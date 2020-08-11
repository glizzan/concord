from django.shortcuts import render, redirect

from concord.actions.utils import Client


def condition_landing_view(request, action_pk):
    client = Client(actor=request.user.username)
    condition = client.Conditional.get_condition_item_given_action(action_pk=action_pk)
    all_actions = client.Action.get_action_history_given_target(target=condition)
    context = {'condition': condition, 'all_actions': all_actions}
    return render(request, 'conditionals/condition_detail.html', context)

def approve_action(request, action_pk):
    client = Client(actor=request.user.username)
    condition = client.Conditional.get_condition_item_given_action(action_pk=action_pk)
    client.ApprovalCondition.set_target(target=condition)
    client.ApprovalCondition.approve()
    return redirect('conditionals:condition_detail', action_pk=action_pk)

# FIXME: probably make approve/reject action one view with selection choice, as with cast_vote
def reject_action(request, action_pk):
    client = Client(actor=request.user.username)
    condition = client.Conditional.get_condition_item_given_action(action_pk=action_pk)
    client.ApprovalCondition.set_target(target=condition)
    client.ApprovalCondition.reject()
    return redirect('conditionals:condition_detail', action_pk=action_pk)

def cast_vote(request, action_pk, selection):
    client = Client(actor=request.user.username)
    condition = client.Conditional.get_condition_item_given_action(action_pk=action_pk)
    client.VoteCondition.set_target(condition)
    if selection in ["yea", "nay", "abstain"]:
        client.VoteCondition.vote(vote=selection)
    else:
        raise ValueError("Vote %s not a legal vote." % selection)
    return redirect('conditionals:condition_detail', action_pk=action_pk)