# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestTrace(MarketingAutomationCommon):
    """Task 6.x — traces and mail-reaction events."""

    def _email_chain(self, partner):
        """An email activity with one child per mail reaction trigger."""
        mailing_model = self.env['ir.model']._get('res.partner')
        mailing = self.env['mailing.mailing'].create({
            'name': 'Trace mailing',
            'subject': 'Subject',
            'mailing_model_id': mailing_model.id,
            'mailing_domain': "[('id','in',[%s])]" % partner.id,
            'body_html': '<p>Hello</p>',
            'use_in_marketing_automation': True,
            'state': 'done',
        })
        campaign = self._create_campaign()
        email = self._create_activity(
            campaign, name='Email', activity_type='email',
            mass_mailing_id=mailing.id)
        action = self._action_server('res.partner')
        children = {}
        for index, trigger in enumerate([
                'mail_open', 'mail_not_open', 'mail_click', 'mail_not_click',
                'mail_reply', 'mail_not_reply', 'mail_bounce']):
            children[trigger] = self._create_activity(
                campaign, name=trigger, activity_type='action',
                server_action_id=action.id, trigger_type=trigger,
                parent_id=email.id, interval_number=index + 1,
                interval_type='hours')
        participant = self._create_participant(campaign, partner)
        email_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == email)
        self._schedule_now(email_trace)
        campaign.execute_activities()
        # The children are created during execution: drop the cached
        # one2many so that participant.trace_ids sees them.
        participant.invalidate_recordset()
        email_trace.invalidate_recordset()
        return campaign, email_trace, children, participant

    def test_6_1_trace_defaults(self):
        """6.1 A trace starts scheduled with the participant and activity."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        activity = self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self.assertEqual(trace.state, 'scheduled')
        self.assertEqual(trace.participant_id, participant)
        self.assertEqual(trace.res_id, partner.id)
        self.assertEqual(trace.model_name, 'res.partner')
        self.assertEqual(trace.activity_type, 'action')
        self.assertEqual(trace.trigger_type, 'begin')

    def test_6_2_trace_cancel_marks_participant(self):
        """6.2 Cancelling the last scheduled trace completes the participant."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids
        trace.action_cancel(message='Test cancel')
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'canceled')
        self.assertIn('Test cancel', trace.state_msg)
        self.assertEqual(participant.state, 'completed')

    def test_6_3_trace_action_execute(self):
        """6.3 action_execute runs the activity on that single trace."""
        partner = self._create_partner()
        action = self._action_server('res.partner', code=(
            "for rec in records:\n"
            "    rec.write({'name': 'executed'})\n"))
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        trace.action_execute()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'processed')
        self.assertEqual(partner.name, 'executed')

    def test_6_4_open_schedules_open_child(self):
        """6.4/6.5 Opening the mail schedules the 'opened' branch."""
        partner = self._create_partner(email='open@example.com')
        campaign, email_trace, children, participant = self._email_chain(
            partner)
        # The email trace needs a mailing.trace to react on.
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': email_trace.activity_id.mass_mailing_id.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email,
        })
        mailing_trace.set_opened()
        open_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_open'])
        not_open_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_not_open'])
        self.assertTrue(open_trace)
        self.assertEqual(open_trace.state, 'scheduled')
        # The opposite branch is cancelled.
        not_open_trace.invalidate_recordset()
        self.assertEqual(not_open_trace.state, 'canceled')

    def test_6_5_click_schedules_click_child(self):
        """6.5 Clicking schedules the 'clicked' branch."""
        partner = self._create_partner(email='click@example.com')
        campaign, email_trace, children, participant = self._email_chain(
            partner)
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': email_trace.activity_id.mass_mailing_id.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email,
        })
        mailing_trace.set_clicked()
        click_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_click'])
        not_click_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_not_click'])
        self.assertTrue(click_trace)
        self.assertEqual(click_trace.state, 'scheduled')
        not_click_trace.invalidate_recordset()
        self.assertEqual(not_click_trace.state, 'canceled')

    def test_6_6_reply_schedules_reply_child(self):
        """6.6 Replying schedules the 'replied' branch."""
        partner = self._create_partner(email='reply@example.com')
        campaign, email_trace, children, participant = self._email_chain(
            partner)
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': email_trace.activity_id.mass_mailing_id.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email,
        })
        mailing_trace.set_replied()
        reply_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_reply'])
        not_reply_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_not_reply'])
        self.assertTrue(reply_trace)
        self.assertEqual(reply_trace.state, 'scheduled')
        not_reply_trace.invalidate_recordset()
        self.assertEqual(not_reply_trace.state, 'canceled')

    def test_6_7_bounce_cancels_all_branches(self):
        """6.7 A bounce cancels every other reaction branch."""
        partner = self._create_partner(email='bounce@example.com')
        campaign, email_trace, children, participant = self._email_chain(
            partner)
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': email_trace.activity_id.mass_mailing_id.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email,
        })
        mailing_trace.set_bounced()
        others = participant.trace_ids.filtered(
            lambda t: t.activity_id in children.values()
            and t.activity_id.trigger_type != 'mail_bounce')
        for trace in others:
            trace.invalidate_recordset()
            self.assertEqual(trace.state, 'canceled')
            self.assertIn('bounced', trace.state_msg)

    def test_6_8_zero_interval_executes_immediately(self):
        """6.8 A child with interval 0 runs as soon as the event arrives."""
        partner = self._create_partner(email='now@example.com')
        mailing_model = self.env['ir.model']._get('res.partner')
        mailing = self.env['mailing.mailing'].create({
            'name': 'Immediate',
            'subject': 'Subject',
            'mailing_model_id': mailing_model.id,
            'mailing_domain': "[('id','in',[%s])]" % partner.id,
            'body_html': '<p>Hello</p>',
            'use_in_marketing_automation': True,
            'state': 'done',
        })
        action = self._action_server('res.partner', code=(
            "for rec in records:\n"
            "    rec.write({'name': 'opened now'})\n"))
        campaign = self._create_campaign()
        email = self._create_activity(
            campaign, name='Email', activity_type='email',
            mass_mailing_id=mailing.id)
        child = self._create_activity(
            campaign, name='Open now', activity_type='action',
            server_action_id=action.id, trigger_type='mail_open',
            parent_id=email.id, interval_number=0)
        participant = self._create_participant(campaign, partner)
        email_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == email)
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': mailing.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email,
        })
        self._schedule_now(email_trace)
        campaign.execute_activities()
        participant.invalidate_recordset()
        mailing_trace.set_opened()
        child_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == child)
        child_trace.invalidate_recordset()
        self.assertEqual(child_trace.state, 'processed')
        self.assertEqual(partner.name, 'opened now')

    def test_6_9_process_event_respects_campaign_state(self):
        """6.9 A stopped campaign ignores incoming events."""
        partner = self._create_partner(email='stopped@example.com')
        campaign, email_trace, children, participant = self._email_chain(
            partner)
        campaign.action_stop_campaign()
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': email_trace.activity_id.mass_mailing_id.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email,
        })
        mailing_trace.set_opened()
        open_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == children['mail_open'])
        open_trace.invalidate_recordset()
        self.assertEqual(open_trace.state, 'scheduled')

    def test_6_10_mailing_trace_link(self):
        """6.10 The extension adds marketing_trace_id to mailing.trace."""
        field = self.env['mailing.trace']._fields.get('marketing_trace_id')
        self.assertTrue(field, "marketing_trace_id not added to mailing.trace")
        self.assertEqual(field.comodel_name, 'marketing.trace')

    def test_6_11_update_schedule_date(self):
        """6.11 Changing an interval reschedules the pending traces."""
        partner = self._create_partner()
        action = self._action_server('res.partner')
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            interval_number=1, interval_type='days')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        before = trace.schedule_date
        activity.write({'interval_number': 3})
        trace._update_schedule_date()
        trace.invalidate_recordset()
        self.assertNotEqual(trace.schedule_date, before)
        self.assertAlmostEqual(
            trace.schedule_date,
            participant.create_date + relativedelta(days=3),
            delta=relativedelta(seconds=5))
