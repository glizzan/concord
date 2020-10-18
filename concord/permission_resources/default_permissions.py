from concord.actions.utils import Changes


DEFAULT_PERMISSIONS = {
    "community": [
        {"permission_type": Changes().Resources.AddComment,
         "permission_roles": ["members"],
         "permission_configuration": {"target_type": "action"}},
        {"permission_type": Changes().Actions.ApplyTemplate,
         "permission_roles": ["members"],
         "permission_configuration": {"original_creator_only": True}},
        {"permission_type": Changes().Communities.AddMembers,
         "anyone": True, "permission_configuration": {"self_only": True},
         "condition": {"condition_type": "approvalcondition",
                       "permission_data": [
                           {"permission_type": Changes().Conditionals.Approve, "permission_roles": ["governors"]},
                           {"permission_type": Changes().Conditionals.Reject, "permission_roles": ["governors"]}
                       ]}
         }
    ],
    "comment": [
    ]
    # "simplelist": [
    #     {"permission_type": Changes().Resources.EditList,
    #      "permission_roles": ["members"],
    #      "permission_configuration": {"original_creator_only": True}},
    #     {"permission_type": Changes().Resources.DeleteList,
    #      "permission_roles": ["members"],
    #      "permission_configuration": {"original_creator_only": True}},
    #     {"permission_type": Changes().Resources.AddRow,
    #      "permission_roles": ["members"],
    #      "permission_configuration": {"original_creator_only": True}},
    #     {"permission_type": Changes().Resources.EditRow,
    #      "permission_roles": ["members"],
    #      "permission_configuration": {"original_creator_only": True}},
    #     {"permission_type": Changes().Resources.MoveRow,
    #      "permission_roles": ["members"],
    #      "permission_configuration": {"original_creator_only": True}},
    #      {"permission_type": Changes().Resources.DeleteRow,
    #      "permission_roles": ["members"],
    #      "permission_configuration": {"original_creator_only": True}}
    # ]
}
