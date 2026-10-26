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
  return <article className="card friends-panel">
    <h3>Owner & members</h3>
    {data.members.map(member => <div className="social-row" key={member.id}><span><strong>{member.name}</strong> · {member.role} · {member.email}</span>
      {member.role !== "owner" && <button className="secondary" disabled={busy} onClick={async () => {
        setBusy(true);
        try { await removeCampaignMember(campaignId, member.id); await refresh(); setFeedback("Member removed."); }
        catch { setFeedback("Could not remove member."); }
        finally { setBusy(false); }
      }}>Remove member</button>}
    </div>)}
    <h3>Invite to campaign</h3>
    <p>Invitations expire after 7 days. Invitees accept from Friends & invitations. Player and viewer access currently includes approved canon only.</p>
    <form onSubmit={async event => {
      event.preventDefault(); if (busy) return; setBusy(true); setFeedback("");
      try { await inviteToCampaign(campaignId, email, role); setEmail(""); await refresh(); setFeedback("Invitation created. Ask them to sign in or register with this email to accept it."); }
      catch (error) { setFeedback(error instanceof Error ? error.message : "Could not invite."); }
      finally { setBusy(false); }
    }}>
      {friends.length > 0 && <label>Choose a friend<select value="" onChange={e => setEmail(e.target.value)}><option value="">Select a friend…</option>{friends.map(f => <option key={f.id} value={f.user.email}>{f.user.name}</option>)}</select></label>}
      <label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
      <label>Role<select value={role} onChange={e => setRole(e.target.value)}><option value="player">Player</option><option value="viewer">Viewer</option></select></label>
      <button disabled={busy}>Send invitation</button>
    </form>
    {data.invitations.length > 0 && <h3>Pending invitations</h3>}
    {data.invitations.map(invite => <div className="social-row" key={invite.id}><span>{invite.email} · {invite.role}</span><button className="secondary" disabled={busy} onClick={async () => {
      setBusy(true);
      try { await declineInvitation(invite.id); await refresh(); setFeedback("Invitation revoked."); }
      catch { setFeedback("Could not revoke invitation."); }
      finally { setBusy(false); }
    }}>Revoke</button></div>)}
    {feedback && <p role="status">{feedback}</p>}
  </article>;
}
