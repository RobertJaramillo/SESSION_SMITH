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
  return <section className="card friends-panel" aria-label="Friends and invitations">
    <h2>Friends & invitations</h2>
    <p>Add a friend by their account email. Campaign invitations appear here when you sign in with the invited email.</p>
    <form className="button-row" onSubmit={event => { event.preventDefault(); void act(async () => { await addFriend(email.trim()); setEmail(""); }, "Friend request sent."); }}>
      <label>Friend’s email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="friend@example.com" /></label>
      <button disabled={busy} type="submit">Send friend request</button>
    </form>
    {loading && <p role="status">Loading friends…</p>}
    <div className="two-column">
      <div><h3>Your friends</h3>
        {!loading && !friends.length && <p>No friends yet. Send a request to start your party.</p>}
        {friends.map(friend => <article className="social-row" key={friend.id}>
          <div><strong>{friend.user.name}</strong><p>{friend.user.email}</p><small>{friend.status === "accepted" ? "Friend" : friend.incoming ? "Wants to be your friend" : "Request sent"}</small></div>
          <div className="button-row">
            {friend.status === "pending" && friend.incoming && <button disabled={busy} onClick={() => void act(() => acceptFriend(friend.id), "Friend request accepted.")}>Accept</button>}
            <button className="secondary" disabled={busy} onClick={() => void act(() => removeFriend(friend.id), friend.status === "accepted" ? "Friend removed." : "Request dismissed.")}>{friend.status === "accepted" ? "Remove friend" : friend.incoming ? "Decline" : "Cancel request"}</button>
          </div>
        </article>)}
      </div>
      <div><h3>Campaign invitations</h3>
        {!loading && !invitations.length && <p>No pending campaign invitations.</p>}
        {invitations.map(invite => <article className="social-row" key={invite.id}>
          <div><strong>{invite.campaignName}</strong><p>{invite.sender_name} invited you as a {invite.role}.</p></div>
          <div className="button-row">
            <button disabled={busy} onClick={() => void act(async () => { await acceptInvitation(invite.id); onJoined(); }, "Campaign joined. Find it under Shared.")}>Join campaign</button>
            <button className="secondary" disabled={busy} onClick={() => void act(() => declineInvitation(invite.id), "Invitation declined.")}>Decline</button>
          </div>
        </article>)}
      </div>
    </div>
    {feedback && <p role="status">{feedback}</p>}
  </section>;
}
