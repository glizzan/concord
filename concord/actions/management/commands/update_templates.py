"""Management command which updates the template library."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Updates the template library to include new templates'

    def add_arguments(self, parser):
        # Named (optional) arguments
        parser.add_argument(
            '--recreate',
            action='store_true',
            help='Recreate all templates from scratch',
        )
        # Named (optional) arguments
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print status to stdout',
        )

    def handle(self, *args, **options):

        from concord.actions.models import TemplateModel
        from concord.utils.lookups import get_all_templates

        if options['recreate']:
            for template in TemplateModel.objects.all():
                template.delete()
            if options['verbose']:
                self.stdout.write(self.style.SUCCESS('deleted existing templates'))

        for template_class in get_all_templates():

            if not options['recreate']:

                template_model = template_class().return_if_exists()
                if template_model:
                    if options['verbose']:
                        self.stdout.write(self.style.SUCCESS('Skipping existing template "%s"' % template_model.name))
                    continue

            template_model = template_class().create_template_model()
            if options['verbose']:
                self.stdout.write(self.style.SUCCESS('Created template "%s"' % template_model.name))
