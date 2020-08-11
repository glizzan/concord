from concord.actions.utils import Changes, Client


def get_membership_setting(actor, community):

    client = Client(actor=actor, target=community)

    # get permission 

    permissions = client.PermissionResource.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")

    if len(permissions) == 0:
        return "no new members can join", None, None
    
    permission = permissions[0]

    # Check for condition

    condition = client.Conditional.get_conditions_given_targets(target_pks=[permission.pk])
    
    if permission.anyone:

        if condition:
            return "anyone can ask", permission, condition[0]
        else:
            return "anyone can join", permission, None
    
    else:
        return "invite only", permission, condition[0]
