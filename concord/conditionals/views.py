from django.shortcuts import render, redirect

from concord.actions.client import ActionClient
from concord.conditionals.client import (ConditionalClient, ApprovalConditionClient,
    VoteConditionClient)


def condition_landing_view(request, action_pk):
    pcc = ConditionalClient(actor=request.user.username)
    condition = pcc.get_condition_item_given_action(action_pk=action_pk)
    all_actions = ActionClient(actor=request.user.username).get_action_history_given_target(target=condition)
    context = {'condition': condition, 'all_actions': all_actions}
    return render(request, 'conditionals/condition_detail.html', context)

def approve_action(request, action_pk):
    pcc = ConditionalClient(actor=request.user.username)
    condition = pcc.get_condition_item_given_action(action_pk=action_pk)
    acc = ApprovalConditionClient(actor=request.user.username, target=condition)
    acc.approve()
    return redirect('conditionals:condition_detail', action_pk=action_pk)

# FIXME: probably make approve/reject action one view with selection choice, as with cast_vote
def reject_action(request, action_pk):
    pcc = ConditionalClient(actor=request.user.username)
    condition = pcc.get_condition_item_given_action(action_pk=action_pk)
    acc = ApprovalConditionClient(actor=request.user.username, target=condition)
    acc.reject()
    return redirect('conditionals:condition_detail', action_pk=action_pk)

def cast_vote(request, action_pk, selection):
    pcc = ConditionalClient(actor=request.user.username)
    condition = pcc.get_condition_item_given_action(action_pk=action_pk)
    vcc = VoteConditionClient(actor=request.user.username, target=condition)
    if selection in ["yea", "nay", "abstain"]:
        vcc.vote(vote=selection)
    else:
        raise ValueError("Vote %s not a legal vote." % selection)
    return redirect('conditionals:condition_detail', action_pk=action_pk)