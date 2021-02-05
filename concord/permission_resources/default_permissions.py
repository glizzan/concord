from concord.utils.helpers import Changes


DEFAULT_PERMISSIONS = {
    "community": [
        {"change_type": Changes().Resources.AddComment,
         "roles": ["members"],
         "configuration": {"target_type": "action"}},
        {"change_type": Changes().Actions.ApplyTemplate,
         "roles": ["members"],
         "configuration": {"original_creator_only": True}},
        {"change_type": Changes().Communities.AddMembers,
         "anyone": True, "configuration": {"self_only": True},
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
