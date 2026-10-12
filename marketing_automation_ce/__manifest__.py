# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    'name': 'Marketing Automation CE',
    'version': '18.0.1.0.0',
    'summary': 'Marketing automation flow engine on Community Edition',
    'category': 'Marketing/Marketing Automation',
    'description': """
Marketing Automation CE
=======================

Flow engine for Odoo Community Edition: build multi-step campaigns that
send email and run server actions in sequence or as branches, with
condition waits, goal steps and an explicit re-enrollment policy, and
follow every participant's path through the flow with traceable run
history and per-activity statistics.

Capabilities:

* Campaigns with a target model, filter and status.
* Activity trees with nine trigger types: begin, previous activity, and the
  seven mail reactions (opened, not opened, clicked, not clicked, replied,
  not replied, bounced).
* Condition steps: evaluate a domain against the participant's record and
  pick a branch, optionally waiting until the condition holds with a
  timeout.
* Goal steps: a campaign goal domain that ends a participant's flow.
* Explicit re-enrollment policy: never, once, or after a delay.
* Participant synchronisation with uniqueness filtering.
* Trace-based run history, per-activity statistics and a campaign template
  library.
""",
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-mass_mailing/marketing_automation_ce',
    'images': ['static/description/banner.png'],
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-mass_mailing',
    'depends': ['mass_mailing'],
    'data': [
        'security/marketing_automation_security.xml',
        'security/ir.model.access.csv',
        'views/marketing_automation_menus.xml',
        'views/marketing_participant_views.xml',
        'views/marketing_activity_views.xml',
        'views/marketing_campaign_views.xml',
        'views/marketing_trace_views.xml',
        'views/mailing_mailing_views.xml',
        'data/ir_cron_data.xml',
        'data/marketing_automation_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'marketing_automation_ce/static/src/**/*',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': True,
}
