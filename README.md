# Concord

Concord is a framework for implementing user-controlled permissions and governance structures. Sites built with Concord allow communities of users to determine which actions may be taken in their communities using a variety of decision-making processes.

To learn more about the design and implementation of Concord, check out [our documentation](https://glizzan-concord.readthedocs.io/en/latest/).

The project is maintained by the [Glizzan organization](https://www.glizzan.com/) and surrounding community. To join, please email glizzanplatform@gmail.com to ask for an invite to [our Zulip discussion space](https://glizzan.zulipchat.com/). Please note: this project uses the [Contributor Covenant](https://www.contributor-covenant.org/version/2/0/code_of_conduct/) as our Code of Conduct, and by participating you agree to abide by its terms.

Concord has been released under a custom license, the [Concord Cooperative License](https://github.com/glizzan/glizzan-concord/blob/master/license.md). This license is more restrictive than a free software/open source license. If you believe that your intended use might not fall under the terms of that license, please contact us to discuss alternatives.

## Installing Concord

1. Make a directory for your project `mkdir glizzan`
1. Change into the directory: `cd glizzan`
1. Fork the repo on GitHub
1. Clone your fork: `git clone <your name>/glizzan-concord`
1. Change into directory you just cloned: `cd glizzan-concord`
1. Create a Python3 virtual environment: `python3 -m venv testenv`
1. Activate the virtual environment: `source testenv/bin/activate`
1. Check pip for upgrades: `pip install --upgrade pip`
1. Install requirements: `pip install -r requirements.txt`
1. Change into subdirectory where tests are: `cd concord`
1. Run the tests: `python manage.py test`

## Testing

There are two types of tests to run.

Testing of the core module is done via pytest. Make sure you are in the core directory and run `python -m pytest`.

Otherwise testing is run as you would expect in a Django project, by cding into the project (Concord) and running `python manage.py test`.

## Contributing to Concord

It is emphatically recommended that you join the community before trying to make a contribution. Concord is still in an early stage of development and contains many hacks and quirks that you will likely need to ask questions about.

Nevertheless, it's worth sketching out a number of the ways in which you can contribute to this project:

* using Concord or any of its implementations and providing feedback about the experience
* improving documentation, including by reading the existing documentation and telling us if any parts confused you
* providing security, accessibility and/or performance reviews
* adding to the test suites
* writing new features or fixing bugs

In particular, Concord is built to be extensible in three major ways: through the addition of new templates, new condition types, and new resource types. Please see the Documentation for how to do so: [How to Add a Template](https://glizzan-concord.readthedocs.io/en/latest/how_to_add_template.html), [How to Add a Resource](https://glizzan-concord.readthedocs.io/en/latest/how_to_add_resource.html), [How to Add a Condition]() (coming soon).
