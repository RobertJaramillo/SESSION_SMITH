import { useEffect, useState } from "react";
import { acceptFriend, acceptInvitation, addFriend, declineInvitation, listFriends, listInvitations, removeFriend, type Friendship, type CampaignInvitation } from "../api/client";

export function FriendsPanel({ onJoined }: { onJoined: () => void }) {
  const [friends, setFriends] = useState<Friendship[]>([]);
  const [invitations, setInvitations] = useState<CampaignInvitation[]>([]);
  const [email, setEmail] = useState("");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const refresh = async () => {
    const [f, i] = await Promise.all([listFriends(), listInvitations()]);
    setFriends(f); setInvitations(i);
  };
  useEffect(() => {
    Promise.all([listFriends(), listInvitations()]).then(([f, i]) => { setFriends(f); setInvitations(i); }).catch(() => setFeedback("Could not load friends and invitations.")).finally(() => setLoading(false));
  }, []);
  const act = async (action: () => Promise<unknown>, message: string) => {
    if (busy) return;
    setBusy(true); setFeedback("");
    try { await action(); await refresh(); setFeedback(message); }
    catch (error) { setFeedback(error instanceof Error ? error.message : "Please try again."); }
    finally { setBusy(false); }
  };
  return <section className="card friends-panel social-panel" aria-label="Friends and invitations">
    <div className="social-panel-heading"><div><span className="eyebrow">Your party</span><h2>Friends & invitations</h2><p>Bring your people to the table.</p></div><span className="social-count">{friends.filter(f => f.status === "accepted").length} {friends.filter(f => f.status === "accepted").length === 1 ? "friend" : "friends"}</span></div>
    <form className="social-composer" onSubmit={event => { event.preventDefault(); void act(async () => { await addFriend(email.trim()); setEmail(""); }, "Friend request sent."); }}>
      <label>Friend’s email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="friend@example.com" /></label>
      <button disabled={busy} type="submit">Send friend request</button>
    </form>
    {loading && <p role="status">Loading friends…</p>}
    <div className="social-columns">
      <div className="social-list"><div className="social-list-heading"><h3>Your friends</h3><span>{friends.length}</span></div>
        {!loading && !friends.length && <div className="social-empty"><span aria-hidden="true">✧</span><strong>Your party starts here</strong><p>No friends yet. Send a request to start your party.</p></div>}
        {friends.map(friend => <article className="social-row" key={friend.id}>
          <div className="social-person"><span className="social-avatar" aria-hidden="true">{friend.user.name.slice(0, 2).toUpperCase()}</span><div><strong>{friend.user.name}</strong><p>{friend.user.email}</p><small className="social-detail">{friend.status === "accepted" ? "Friend" : friend.incoming ? "Wants to be your friend" : "Request sent"}</small></div></div>
          <div className="social-actions">
            {friend.status === "pending" && friend.incoming && <button disabled={busy} onClick={() => void act(() => acceptFriend(friend.id), "Friend request accepted.")}>Accept</button>}
            <button className="social-quiet-button" disabled={busy} onClick={() => void act(() => removeFriend(friend.id), friend.status === "accepted" ? "Friend removed." : "Request dismissed.")}>{friend.status === "accepted" ? "Remove friend" : friend.incoming ? "Decline" : "Cancel request"}</button>
          </div>
        </article>)}
      </div>
      <div className="social-list"><div className="social-list-heading"><h3>Campaign invitations</h3><span>{invitations.length}</span></div>
        {!loading && !invitations.length && <div className="social-empty"><span aria-hidden="true">◇</span><strong>You’re all caught up</strong><p>No pending campaign invitations.</p></div>}
        {invitations.map(invite => <article className="social-row" key={invite.id}>
          <div className="social-invitation-copy"><strong>{invite.campaignName}</strong><p>{invite.sender_name} invited you as a {invite.role}.</p></div>
          <div className="social-actions">
            <button disabled={busy} onClick={() => void act(async () => { await acceptInvitation(invite.id); onJoined(); }, "Campaign joined. Find it under Shared.")}>Join campaign</button>
            <button className="social-quiet-button" disabled={busy} onClick={() => void act(() => declineInvitation(invite.id), "Invitation declined.")}>Decline</button>
          </div>
        </article>)}
      </div>
    </div>
    {feedback && <p className="social-feedback" role="status">{feedback}</p>}
  </section>;
}
