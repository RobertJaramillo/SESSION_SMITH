import { useEffect, useState } from "react";
import { transferCampaignOwnership, removeCampaignMember, declineInvitation, getMembers, inviteToCampaign, listFriends, type CampaignMembers, type Friendship } from "../api/client";

export function CampaignMembersPanel({ campaignId, onTransferred }: { campaignId: string; onTransferred?: () => void }) {
  const [newOwnerId, setNewOwnerId] = useState("");
  const [confirmTransfer, setConfirmTransfer] = useState(false);
  const [transferred, setTransferred] = useState(false);
  const [data, setData] = useState<CampaignMembers>({ members: [], invitations: [] });
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [email, setEmail] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = async () => setData(await getMembers(campaignId));
  useEffect(() => {
    Promise.all([getMembers(campaignId), listFriends()]).then(([members, friends]) => { setData(members); setFriends(friends.filter(f => f.status === "accepted")); }).catch(() => setFeedback("Could not load campaign members."));
  }, [campaignId]);
  if (transferred) return <p role="status">Ownership transferred. You are now a player.</p>;
  return <article className="card friends-panel social-panel">
    <div className="social-panel-heading"><div><span className="eyebrow">The table</span><h3>Owner & members</h3><p>Manage who shares this world.</p></div><span className="social-count">{data.members.length} {data.members.length === 1 ? "member" : "members"}</span></div>
    <div className="sharing-grid"><div className="sharing-roster">
    {data.members.map(member => <div className="social-row" key={member.id}><div className="social-person"><span className="social-avatar" aria-hidden="true">{member.name.slice(0, 2).toUpperCase()}</span><div><strong>{member.name}</strong><p>{member.email}</p></div></div><span className={`social-role social-role-${member.role}`}>{member.role}</span>
      {member.role !== "owner" && <button className="social-quiet-button" disabled={busy} onClick={async () => {
        setBusy(true);
        try { await removeCampaignMember(campaignId, member.id); await refresh(); setFeedback("Member removed."); }
        catch { setFeedback("Could not remove member."); }
        finally { setBusy(false); }
      }}>Remove member</button>}
    </div>)}
    </div><div className="sharing-invite"><h3>Invite to campaign</h3>
    <p>Make room for someone new.</p>
    <form onSubmit={async event => {
      event.preventDefault(); if (busy) return; setBusy(true); setFeedback("");
      try { await inviteToCampaign(campaignId, email, "player"); setEmail(""); await refresh(); setFeedback("Invitation created. Ask them to sign in or register with this email to accept it."); }
      catch (error) { setFeedback(error instanceof Error ? error.message : "Could not invite."); }
      finally { setBusy(false); }
    }}>
      {friends.length > 0 && <label>Choose a friend<select value={friends.some(f => f.user.email === email) ? email : ""} onChange={e => setEmail(e.target.value)}><option value="">Select a friend…</option>{friends.map(f => <option key={f.id} value={f.user.email}>{f.user.name}</option>)}</select></label>}
      <label>Email<input type="email" placeholder="friend@example.com" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      <p className="social-hint">Invited members join as players.</p>
      <button disabled={busy}>Send invitation</button>
    </form>
    <p className="social-hint">Players can read approved canon. Invites appear in their account and expire in 7 days.</p></div></div>
    {data.invitations.length > 0 && <h3 className="sharing-pending-title">Pending invitations</h3>}
    {data.invitations.map(invite => <div className="social-row" key={invite.id}><div className="social-invitation-copy"><strong>{invite.email}</strong><p>Awaiting acceptance</p></div><span className="social-role">{invite.role}</span><button className="social-quiet-button" disabled={busy} onClick={async () => {
      setBusy(true);
      try { await declineInvitation(invite.id); await refresh(); setFeedback("Invitation revoked."); }
      catch { setFeedback("Could not revoke invitation."); }
      finally { setBusy(false); }
    }}>Revoke</button></div>)}
    <section className="ownership-transfer" aria-label="Transfer campaign ownership">
      <h3>Transfer ownership</h3>
      <p>Hand GM control of this campaign to an accepted friend. You’ll remain a player.</p>
      {friends.length ? <>
        <label>New owner<select disabled={busy || confirmTransfer} value={newOwnerId} onChange={event => { setNewOwnerId(event.target.value); setConfirmTransfer(false); }}>
          <option value="">Choose a friend…</option>
          {friends.map(friend => <option key={friend.user.id} value={friend.user.id}>{friend.user.name}</option>)}
        </select></label>
        {!confirmTransfer ? <button type="button" className="secondary" disabled={!newOwnerId || busy} onClick={() => setConfirmTransfer(true)}>Transfer ownership</button> : <div>
          <p role="alert">Make {friends.find(friend => friend.user.id === newOwnerId)?.user.name} the owner? They’ll gain full GM access, including private notes and session prep. You’ll lose owner controls. Only the new owner can transfer it back.</p>
          <div className="ownership-transfer-actions">
            <button type="button" disabled={busy} onClick={async () => {
              if (busy) return;
              setBusy(true); setFeedback("");
              try { await transferCampaignOwnership(campaignId, newOwnerId); setTransferred(true); onTransferred?.(); }
              catch (error) { setFeedback(error instanceof Error ? error.message : "Could not transfer ownership."); }
              finally { setBusy(false); }
            }}>{busy ? "Transferring…" : "Confirm transfer"}</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => setConfirmTransfer(false)}>Cancel transfer</button>
          </div>
        </div>}
      </> : <p className="social-hint">Add a friend and have them accept your request before transferring ownership.</p>}
    </section>
    {feedback && <p className="social-feedback" role="status">{feedback}</p>}
  </article>;
}
