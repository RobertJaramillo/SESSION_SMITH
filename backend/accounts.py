"""Accounts and sharing storage. PostgreSQL in the stack, SQLite in memory for development."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
from threading import RLock
import time
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from starlette.responses import JSONResponse
from backend.db import connect, postgres_enabled

COOKIE = 'session_smith'
SESSION_SECONDS = 60 * 60 * 24 * 7


def fail(message, code=400):
    raise HTTPException(code, detail=message)


def uid():
    return uuid4().hex


def public(user):
    return {k: user[k] for k in ('id', 'name', 'email')}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1).hex()
    return f'{salt}:{digest}'


class Accounts:
    def __init__(self):
        self.lock = RLock()
        self.memory = sqlite3.connect(':memory:', check_same_thread=False)
        self.memory.row_factory = sqlite3.Row
        self.memory.execute('PRAGMA foreign_keys=ON')
        schema = Path(__file__).with_name('migrations').joinpath('007_accounts_and_sharing.sql').read_text()
        # Campaign rows live in the existing development store, outside SQLite.
        schema = schema.replace(' REFERENCES campaigns(id) ON DELETE CASCADE', '')
        self.memory.executescript(schema)

    @contextmanager
    def transaction(self):
        with self.lock:
            if postgres_enabled():
                with connect() as connection:
                    yield lambda sql, args=(): connection.execute(sql, args)
            else:
                with self.memory:
                    yield lambda sql, args=(): self.memory.execute(sql.replace('%s', '?'), args)

    def user_for_token(self, token):
        if not token:
            return None
        with self.transaction() as sql:
            row = sql('SELECT u.* FROM app_users u JOIN account_sessions s ON s.user_id=u.id WHERE s.token_hash=%s AND s.expires_at>%s', (hashlib.sha256(token.encode()).hexdigest(), time.time())).fetchone()
            return dict(row) if row else None

    def role(self, campaign_id, user_id):
        with self.transaction() as sql:
            row = sql('SELECT role FROM campaign_access WHERE campaign_id=%s AND user_id=%s', (campaign_id, user_id)).fetchone()
            return row['role'] if row else None

    def owner(self, campaign_id):
        with self.transaction() as sql:
            row = sql("SELECT u.id,u.name,u.email FROM app_users u JOIN campaign_access a ON a.user_id=u.id WHERE a.campaign_id=%s AND a.role='owner'", (campaign_id,)).fetchone()
            return dict(row) if row else None

    def decorate(self, campaign, user_id):
        return {**campaign, 'role': self.role(campaign['campaignId'], user_id), 'owner': self.owner(campaign['campaignId'])}


accounts = Accounts()
router = APIRouter(prefix='/v1')


class Credentials(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=12, max_length=256)

    @field_validator('email')
    @classmethod
    def email_address(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Enter a valid email address.')
        return value


def validated_email(value):
    try:
        return Credentials.email_address(value)
    except ValueError:
        fail('Enter a valid email address.',422)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=80)

    @field_validator('name')
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Enter a display name.')
        return value.strip()


def current(request):
    return request.state.user


def session_response(user, request, sql):
    token = secrets.token_urlsafe(32)
    sql('DELETE FROM account_sessions WHERE expires_at < %s', (time.time(),))
    old = request.cookies.get(COOKIE, '')
    sql('DELETE FROM account_sessions WHERE token_hash=%s', (hashlib.sha256(old.encode()).hexdigest(),))
    sql('INSERT INTO account_sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)', (hashlib.sha256(token.encode()).hexdigest(), user['id'], time.time()+SESSION_SECONDS))
    response = JSONResponse({'data': public(user)})
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True, samesite='lax', secure=os.getenv('SESSION_COOKIE_SECURE', '').lower() == 'true' or request.url.scheme == 'https')
    return response


@router.post('/auth/register')
def register(payload: Registration, request: Request):
    hashed = password_hash(payload.password)
    with accounts.transaction() as sql:
        # Serialize account creation across API processes as well as threads.
        if postgres_enabled():
            sql('LOCK TABLE app_users IN EXCLUSIVE MODE')
        if sql('SELECT id FROM app_users WHERE email=%s', (payload.email,)).fetchone():
            fail('An account with this email already exists.', 409)
        user = {'id': uid(), 'email': payload.email, 'name': payload.name}
        sql('INSERT INTO app_users(id,email,name,password_hash) VALUES (%s,%s,%s,%s)', (user['id'], user['email'], user['name'], hashed))
        return session_response(user, request, sql)


@router.post('/auth/login')
def login(payload: Credentials, request: Request):
    with accounts.transaction() as sql:
        row = sql('SELECT * FROM app_users WHERE email=%s', (payload.email,)).fetchone()
        stored = row['password_hash'] if row else '0'*32 + ':' + '0'*128
        if not hmac.compare_digest(password_hash(payload.password, stored.split(':')[0]), stored):
            fail('Email or password is incorrect.', 401)
        return session_response(dict(row), request, sql)


@router.get('/auth/me')
def me(request: Request):
    return {'data': public(current(request))}


@router.post('/auth/logout')
def logout(request: Request):
    with accounts.transaction() as sql:
        sql('DELETE FROM account_sessions WHERE token_hash=%s', (hashlib.sha256(request.cookies.get(COOKIE, '').encode()).hexdigest(),))
    response = JSONResponse({'data': None})
    response.delete_cookie(COOKIE)
    return response


class FriendTarget(BaseModel):
    email: str = Field(min_length=3, max_length=254)


@router.get('/friends')
def friends(request: Request):
    user_id = current(request)['id']
    with accounts.transaction() as sql:
        rows = sql('SELECT f.*,u.id AS peer_id,u.name,u.email FROM friendships f JOIN app_users u ON u.id=CASE WHEN f.sender_id=%s THEN f.recipient_id ELSE f.sender_id END WHERE f.sender_id=%s OR f.recipient_id=%s', (user_id,user_id,user_id)).fetchall()
        return {'data': [{'id':r['id'], 'user':{'id':r['peer_id'],'name':r['name'],'email':r['email']}, 'status':r['status'], 'incoming':r['recipient_id']==user_id} for r in rows]}


@router.post('/friends')
def add_friend(payload: FriendTarget, request: Request):
    user_id = current(request)['id']
    with accounts.transaction() as sql:
        peer = sql('SELECT id FROM app_users WHERE email=%s', (payload.email.strip().lower(),)).fetchone()
        if not peer:
            fail('No account found for that email.', 404)
        if peer['id'] == user_id:
            fail('You cannot add yourself.')
        pair = ':'.join(sorted([user_id, peer['id']]))
        friend_id = uid()
        result = sql("INSERT INTO friendships(id,sender_id,recipient_id,status,pair_key) VALUES (%s,%s,%s,'pending',%s) ON CONFLICT(pair_key) DO NOTHING", (friend_id,user_id,peer['id'],pair))
        if not result.rowcount:
            fail('You are already friends or a request is pending.', 409)
    return {'data': {'id':friend_id}}


@router.post('/friends/{friend_id}/accept')
def accept_friend(friend_id: str, request: Request):
    with accounts.transaction() as sql:
        result = sql("UPDATE friendships SET status='accepted' WHERE id=%s AND recipient_id=%s AND status='pending'", (friend_id,current(request)['id']))
        if not result.rowcount:
            fail('Friend request not found.',404)
    return {'data': None}


@router.delete('/friends/{friend_id}')
def remove_friend(friend_id: str, request: Request):
    user_id = current(request)['id']
    with accounts.transaction() as sql:
        result = sql('DELETE FROM friendships WHERE id=%s AND (sender_id=%s OR recipient_id=%s)',(friend_id,user_id,user_id))
        if not result.rowcount:
            fail('Friend request not found.',404)
    return {'data': None}


class Invitation(FriendTarget):
    role: Literal['player','viewer'] = 'player'


@router.post('/campaigns/{campaign_id}/invitations')
def invite(campaign_id: str, payload: Invitation, request: Request):
    from backend.app import _campaign_or_404
    _campaign_or_404(campaign_id)
    user = current(request)
    if accounts.role(campaign_id,user['id']) != 'owner':
        fail('Only the owner can invite people.',403)
    email = validated_email(payload.email)
    if email == user['email']:
        fail('You already own this campaign.')
    with accounts.transaction() as sql:
        if sql('SELECT a.user_id FROM campaign_access a JOIN app_users u ON u.id=a.user_id WHERE a.campaign_id=%s AND u.email=%s',(campaign_id,email)).fetchone():
            fail('This person is already a member.',409)
        sql('DELETE FROM campaign_invitations WHERE expires_at<%s',(time.time(),))
        result = sql('INSERT INTO campaign_invitations(id,campaign_id,sender_id,email,role,expires_at) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(campaign_id,email) DO NOTHING',(uid(),campaign_id,user['id'],email,payload.role,time.time()+SESSION_SECONDS))
        if not result.rowcount:
            fail('An invitation is already pending.',409)
    return {'data': None}


@router.get('/invitations')
def invitations(request: Request):
    from backend.app import campaigns
    with accounts.transaction() as sql:
        rows = sql('SELECT i.*,u.name AS sender_name FROM campaign_invitations i JOIN app_users u ON u.id=i.sender_id WHERE i.email=%s AND i.expires_at>%s',(current(request)['email'],time.time())).fetchall()
        return {'data': [{**dict(r),'campaignName':(campaigns.get(r['campaign_id']) or {}).get('name','Campaign')} for r in rows]}


@router.post('/invitations/{invitation_id}/accept')
def accept_invitation(invitation_id: str, request: Request):
    user = current(request)
    with accounts.transaction() as sql:
        # DELETE RETURNING makes acceptance atomic across processes.
        row = sql('DELETE FROM campaign_invitations WHERE id=%s AND email=%s AND expires_at>%s RETURNING *',(invitation_id,user['email'],time.time())).fetchone()
        if not row:
            fail('Invitation not found or expired.',404)
        sql('INSERT INTO campaign_access(campaign_id,user_id,role) VALUES (%s,%s,%s) ON CONFLICT(campaign_id,user_id) DO NOTHING',(row['campaign_id'],user['id'],row['role']))
    return {'data': None}


@router.delete('/invitations/{invitation_id}')
def decline_invitation(invitation_id: str, request: Request):
    with accounts.transaction() as sql:
        result = sql('DELETE FROM campaign_invitations WHERE id=%s AND (email=%s OR sender_id=%s)',(invitation_id,current(request)['email'],current(request)['id']))
        if not result.rowcount:
            fail('Invitation not found.',404)
    return {'data': None}


@router.get('/campaigns/{campaign_id}/members')
def members(campaign_id: str, request: Request):
    with accounts.transaction() as sql:
        rows = sql('SELECT u.id,u.name,u.email,a.role FROM campaign_access a JOIN app_users u ON u.id=a.user_id WHERE a.campaign_id=%s',(campaign_id,)).fetchall()
        pending = sql('SELECT id,email,role FROM campaign_invitations WHERE campaign_id=%s AND expires_at>%s',(campaign_id,time.time())).fetchall() if accounts.role(campaign_id,current(request)['id']) == 'owner' else []
    return {'data': {'members':[dict(r) for r in rows], 'invitations':[dict(r) for r in pending]}}


@router.delete('/campaigns/{campaign_id}/members/{member_id}')
def remove_member(campaign_id: str, member_id: str, request: Request):
    if accounts.role(campaign_id,current(request)['id']) != 'owner':
        fail('Only the owner can remove members.',403)
    with accounts.transaction() as sql:
        result = sql("DELETE FROM campaign_access WHERE campaign_id=%s AND user_id=%s AND role <> 'owner'",(campaign_id,member_id))
        if not result.rowcount:
            fail('Member not found or is the campaign owner.',404)
    return {'data': None}


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    email: str | None = Field(default=None, max_length=254)
    password: str | None = Field(default=None, min_length=12, max_length=256)
    currentPassword: str = Field(default='', max_length=256)


@router.patch('/auth/me')
def update_profile(payload: ProfilePatch, request: Request):
    user = current(request)
    if (payload.email is not None or payload.password is not None) and not hmac.compare_digest(password_hash(payload.currentPassword,user['password_hash'].split(':')[0]),user['password_hash']):
        fail('Your current password is incorrect.',403)
    name = payload.name.strip() if payload.name is not None else user['name']
    if not name:
        fail('Enter a display name.',422)
    email = validated_email(payload.email) if payload.email is not None else user['email']
    hashed = password_hash(payload.password) if payload.password is not None else user['password_hash']
    with accounts.transaction() as sql:
        if postgres_enabled():
            sql('LOCK TABLE app_users IN EXCLUSIVE MODE')
        if sql('SELECT id FROM app_users WHERE email=%s AND id<>%s',(email,user['id'])).fetchone():
            fail('This email is already in use.',409)
        sql('UPDATE app_users SET name=%s,email=%s,password_hash=%s WHERE id=%s',(name,email,hashed,user['id']))
        if payload.email is not None or payload.password is not None:
            sql('DELETE FROM account_sessions WHERE user_id=%s',(user['id'],))
        return session_response({**user,'name':name,'email':email},request,sql)
