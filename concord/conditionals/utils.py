'''
Creating human readable descriptions if often really verbose so I'm hiding away the really annoyingly complicated
stuff here.
'''

def description_for_passing_approval_condition(fill_dict=None):

    # HACK to prevent key errors & fix formatting :/   FIXME actors should be usernames not pks too
    if fill_dict:
        fill_dict["approve_actors"] = [ str(actor) for actor in fill_dict.get("approve_actors", []) ]
        fill_dict["approve_roles"] = fill_dict.get("approve_roles", [])
        fill_dict["reject_actors"] = [ str(actor) for actor in fill_dict.get("reject_actors", []) ]
        fill_dict["reject_roles"] = fill_dict.get("reject_roles", [])

    if fill_dict and (fill_dict["approve_roles"] or fill_dict["approve_actors"]):
        base_str = "one person "
        if fill_dict["approve_roles"]:
            role_string = "roles " if len(fill_dict["approve_roles"]) > 1 else "role "
            base_str += "with " + role_string + " " +  ", ".join(fill_dict["approve_roles"])
        if fill_dict["approve_actors"]: 
            if fill_dict["approve_roles"]:
                base_str += " (or in list of individuals: " + ", ".join(fill_dict["approve_actors"]) + ")"
            else:
                base_str += "in list of individuals (" + ", ".join(fill_dict["approve_actors"]) + ")"
        base_str += " needs to approve"
        if fill_dict["reject_actors"] or fill_dict["reject_roles"]:
            base_str += ", with no one "
            if fill_dict["reject_roles"]:
                role_string = "roles " if len(fill_dict["reject_roles"]) > 1 else "role "
                base_str += "with " + role_string + " " +  ", ".join(fill_dict["reject_roles"])
            if fill_dict["reject_actors"]:
                if fill_dict["reject_roles"]:
                    base_str += " (or in list of individuals: " +  ", ".join(fill_dict["reject_actors"]) + ")"
                else:
                    base_str += "in list of individuals (" + ", ".join(fill_dict["reject_actors"]) + ")"
            base_str += " rejecting."
        return base_str
    else:
        return "one person needs to approve this action"


def description_for_passing_voting_condition(condition, fill_dict=None):

    # HACK to prevent key errors
    if fill_dict:
        fill_dict["vote_actors"] = [ str(actor) for actor in fill_dict.get("vote_actors", []) ]
        fill_dict["vote_roles"] = fill_dict.get("vote_roles", [])

    if condition.require_majority:
        base_str = "a majority of people "
    else:
        base_str = "a plurality of people "
    if fill_dict and (fill_dict["vote_roles"] or fill_dict["vote_actors"]):
        if fill_dict["vote_roles"]:
            role_string = "roles " if len(fill_dict["vote_roles"]) > 1 else "role "
            base_str += "with " + role_string + " " +  ", ".join(fill_dict["vote_roles"])
        if fill_dict["vote_actors"]:
            if fill_dict["vote_roles"]:
                base_str += " (or in list of individuals: " + ", ".join(fill_dict["vote_actors"]) + ")"
            else:
                base_str += "in list of individuals (" + ", ".join(fill_dict["vote_actors"]) + ")"
    base_str += " vote for it within %s" % condition.describe_voting_period()
    return base_str