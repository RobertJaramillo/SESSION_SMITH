import { useEffect, useState } from "react";
import { removeCampaignMember, declineInvitation, getMembers, inviteToCampaign, listFriends, type CampaignMembers, type Friendship } from "../api/client";

export function CampaignMembersPanel({ campaignId }: { campaignId: string }) {
  const [data, setData] = useState<CampaignMembers>({ members: [], invitations: [] });
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("player");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = async () => setData(await getMembers(campaignId));
  useEffect(() => {
    Promise.all([getMembers(campaignId), listFriends()]).then(([members, friends]) => { setData(members); setFriends(friends.filter(f => f.status === "accepted")); }).catch(() => setFeedback("Could not load campaign members."));
  }, [campaignId]);
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
      try { await inviteToCampaign(campaignId, email, role); setEmail(""); await refresh(); setFeedback("Invitation created. Ask them to sign in or register with this email to accept it."); }
      catch (error) { setFeedback(error instanceof Error ? error.message : "Could not invite."); }
      finally { setBusy(false); }
    }}>
      {friends.length > 0 && <label>Choose a friend<select value={friends.some(f => f.user.email === email) ? email : ""} onChange={e => setEmail(e.target.value)}><option value="">Select a friend…</option>{friends.map(f => <option key={f.id} value={f.user.email}>{f.user.name}</option>)}</select></label>}
      <label>Email<input type="email" placeholder="friend@example.com" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Role<select value={role} onChange={e => setRole(e.target.value)}><option value="player">Player</option><option value="viewer">Viewer</option></select></label>
      <button disabled={busy}>Send invitation</button>
    </form>
    <p className="social-hint">Players and viewers can read approved canon. Invites appear in their account and expire in 7 days.</p></div></div>
    {data.invitations.length > 0 && <h3 className="sharing-pending-title">Pending invitations</h3>}
    {data.invitations.map(invite => <div className="social-row" key={invite.id}><div className="social-invitation-copy"><strong>{invite.email}</strong><p>Awaiting acceptance</p></div><span className="social-role">{invite.role}</span><button className="social-quiet-button" disabled={busy} onClick={async () => {
      setBusy(true);
      try { await declineInvitation(invite.id); await refresh(); setFeedback("Invitation revoked."); }
      catch { setFeedback("Could not revoke invitation."); }
      finally { setBusy(false); }
    }}>Revoke</button></div>)}
    {feedback && <p className="social-feedback" role="status">{feedback}</p>}
  </article>;
}
