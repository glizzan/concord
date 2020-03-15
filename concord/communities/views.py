from django.shortcuts import render, redirect
from django.http import JsonResponse
import json

from concord.communities.client import CommunityClient
from concord.conditionals.client import CommunityConditionalClient


def get_community_client(request, community_pk):
    comClient = CommunityClient(actor=request.user.username)
    comClient.set_target_community(community_pk=community_pk)
    return comClient

def update_owners(request, community_pk):

    comClient = get_community_client(request, community_pk)
    data = json.loads(request.body)
    actions = comClient.update_owners(new_owner_data={
        "individuals": data["actors"], "roles": data["roles"]})

    # FIXME: I'm not sure this works logically - if one fails, will all 
    # subsequent fail?
    success = True
    error_message = ""
    for action in actions:
        if action.status is not "implemented":
            success = False
            error_message = action.log
            break

    return JsonResponse(data={"success": success, "errors": error_message})

def update_governors(request, community_pk):

    comClient = get_community_client(request, community_pk)
    data = json.loads(request.body)
    actions = comClient.update_governors(new_governor_data={
        "individuals": data["actors"], "roles": data["roles"]})

    # FIXME: I'm not sure this works logically - if one fails, will all 
    # subsequent fail?
    success = True
    error_message = ""
    for action in actions:
        if action.status is not "implemented":
            success = False
            error_message = action.log
            break

    return JsonResponse(data={"success": success, "errors": error_message})


def delete_condition():
    # if condition exists, delete it
    ...

def update_owner_condition(request, community_pk):

    # Get conditional client with correct target, and try to get template
    community = CommunityClient(actor=request.user.username).get_community(community_pk=community_pk)
    condClient = CommunityConditionalClient(actor=request.user.username, target=community)
    template = condClient.get_condition_template_for_owner()

    data = json.loads(request.body)

    # FIXME: I'm not sure this works logically - if one fails, will all 
    # subsequent fail?
    success = True
    error_message = ""

    # If template does not exist, create using data
    if not template:
        action, result = condClient.add_condition_to_owners(
            condition_type=data["condition_type"],  
            permission_data=data["permission_data"], 
            condition_data=data["condition_data"])

        if action.status is not "implemented":
            success = False
            error_message = action.log

        return JsonResponse(data={"success": success, "errors": error_message})

    # If condition does exist, update it.

    return JsonResponse(data={"success": success, "errors": error_message})

def update_governor_condition():
    pass

