from concord.utils.helpers import Changes


DEFAULT_PERMISSIONS = {
    "community": [
        {"change_type": Changes().Resources.AddComment,
         "roles": ["members"],
         "conditions": [{"condition_type": "TargetTypeFilter", "condition_data": {"target_type": "action"}}]},
        {"change_type": Changes().Actions.ApplyTemplate,
         "roles": ["members"],
         "conditions": [{"condition_type": "CreatorFilter"}]},
        {"change_type": Changes().Communities.AddMembers,
         "anyone": True,
         "conditions": [
            {"condition_type": "approvalcondition",
                "permission_data": [
                        {"permission_type": Changes().Conditionals.Approve, "permission_roles": ["governors"]},
                        {"permission_type": Changes().Conditionals.Reject, "permission_roles": ["governors"]}]},
            {"condition_type": "SelfMembershipOnly"}
         ]}
    ],
    "comment": [
    ]
}
