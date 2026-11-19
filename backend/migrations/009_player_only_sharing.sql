-- Preserve existing memberships and invitations while retiring the viewer role.
UPDATE campaign_access SET role = 'player' WHERE role = 'viewer';
UPDATE campaign_invitations SET role = 'player' WHERE role = 'viewer';
ALTER TABLE campaign_access DROP CONSTRAINT campaign_access_role_check;
ALTER TABLE campaign_access ADD CONSTRAINT campaign_access_role_check CHECK (role IN ('owner', 'player'));
ALTER TABLE campaign_invitations DROP CONSTRAINT campaign_invitations_role_check;
ALTER TABLE campaign_invitations ADD CONSTRAINT campaign_invitations_role_check CHECK (role = 'player');
