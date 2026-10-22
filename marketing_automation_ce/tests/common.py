# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import Form, TransactionCase, tagged


@tagged('post_install', '-at_install')
class MarketingAutomationCommon(TransactionCase):
    """Shared fixtures for the flow engine tests.

    The engine is tested against ``res.partner`` because it is the simplest
    model that is a mail thread; ``mailing.contact`` is used where the mailing
    model has to be a mailing-specific one.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partner_model_id = cls.partner_model.id
        cls.group_user = cls.env.ref(
            'marketing_automation_ce.group_marketing_automation_user')

    # ── Fixtures ────────────────────────────────────────────────────────

    @classmethod
    def _create_campaign(cls, **values):
        vals = {
            'title': 'Test Campaign',
            'model_id': cls.partner_model_id,
            'domain': "[]",
        }
        vals.update(values)
        return cls.env['marketing.campaign'].create(vals)

    @classmethod
    def _create_activity(cls, campaign, **values):
        """Create a step.

        An ``action`` step requires a server action and a ``mail`` step
        requires a mailing, so a default server action is created on demand
        when the caller asks for an action step without supplying one.
        """
        vals = {
            'name': 'Activity',
            'campaign_id': campaign.id,
            'activity_type': 'action',
            'trigger_type': 'begin',
        }
        vals.update(values)
        if vals.get('activity_type') == 'action' \
                and not vals.get('server_action_id'):
            vals['server_action_id'] = cls._action_server(
                campaign.model_name or 'res.partner').id
        return cls.env['marketing.activity'].create(vals)

    @classmethod
    def _create_partner(cls, **values):
        vals = {'name': 'Participant'}
        vals.update(values)
        return cls.env['res.partner'].create(vals)

    @classmethod
    def _create_participant(cls, campaign, record, **values):
        vals = {
            'campaign_id': campaign.id,
            'res_id': record.id,
        }
        vals.update(values)
        return cls.env['marketing.participant'].create(vals)

    @classmethod
    def _action_server(cls, model, code='pass', name='Test action'):
        return cls.env['ir.actions.server'].create({
            'name': name,
            'model_id': cls.env['ir.model']._get(model).id,
            'state': 'code',
            'code': code,
        })

    # ── Helpers ─────────────────────────────────────────────────────────

    def _schedule_now(self, traces, **values):
        """Back-date traces so that ``execute`` picks them up."""
        vals = {'schedule_date': fields.Datetime.now() - relativedelta(
            minutes=1)}
        vals.update(values)
        traces.write(vals)
        return traces

    def _run(self, campaign):
        """Run every due activity of the campaign."""
        return campaign.execute_activities()

    def _assert_trace_state(self, trace, state, msg=None):
        trace.invalidate_recordset()
        self.assertEqual(
            trace.state, state,
            f"{trace.activity_id.name}: {trace.state_msg or ''}")
        if msg:
            self.assertIn(msg, trace.state_msg or '')
