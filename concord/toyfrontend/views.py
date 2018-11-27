from django.views import generic

from resources.client import ResourceClient
rcc = ResourceClient(actor="view_only")  # UGH
from actions.clients import BaseActionClient
acc = BaseActionClient(actor="view_only")


######################
### Resource Views ###
######################

# List of all resources
class ResourceListView(generic.ListView):
    template_name = 'toyfrontend/resource_list.html'

    def get_queryset(self):
        return rcc.get_all_resources()

# List of all resources by an owner
class ResourceListByOwnerView(generic.ListView):
    template_name = 'toyfrontend/resource_list.html'

    def get_queryset(self):
        return rcc.get_all_resources_given_owner(owner_name=self.kwargs['owner_name'])

# Detail view for resource with all items
class ResourceDetailView(generic.DetailView):
    template_name = 'toyfrontend/resource_detail.html'

    def get_queryset(self):
        return rcc.get_resource_given_pk(pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.get_queryset():
            target=self.get_queryset().first()
        context['actions'] = acc.get_action_history_given_target(target)
        return context



# Detail view of an item

# Create resource view?  Add item to resource view?


######################################
### Permissions & Conditions Views ###
######################################

# Show permissions resource of an item

# Edit permissions on an item?

# Add condition to an item?

# Add permissioned condition to an item?


#####################
### Actions Views ###
#####################

# Show all actions (w/ 'show only active actions' option?)

# Show all actions on a target

# Show all actions by an actor

# Conditional Item view?

# Take action on a conditional item view?
