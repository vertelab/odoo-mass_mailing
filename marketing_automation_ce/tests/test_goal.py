# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestGoal(MarketingAutomationCommon):
    """Task 5.6 — the goal stops the flow."""

    def test_goal_1_field_configuration(self):
        """The campaign exposes goal_domain and the participant the flag."""
        campaign_field = self.env['marketing.campaign']._fields['goal_domain']
        self.assertEqual(campaign_field.type, 'char')
        trace_field = self.env['marketing.trace']._fields['goal_met']
        self.assertEqual(trace_field.type, 'boolean')
        self.assertTrue(trace_field.store)

    def test_goal_2_met_on_manual_write(self):
        """goal_met follows the record without any execution pass."""
        partner = self._create_partner(function=False)
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        activity = self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self.assertFalse(trace.goal_met)
        partner.write({'function': 'cto'})
        # goal_met cannot depend on the target model's fields (they are only
        # known at runtime), so the campaign must recompute it explicitly.
        campaign._recompute_goals()
        trace.invalidate_recordset()
        self.assertTrue(trace.goal_met)

    def test_goal_3_participant_completed_on_goal(self):
        """Reaching the goal completes the participant's flow."""
        partner = self._create_partner(function='cto')
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        activity = self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self._schedule_now(trace)
        campaign.execute_activities()
        trace.invalidate_recordset()
        participant.invalidate_recordset()
        self.assertEqual(trace.state, 'canceled')
        self.assertIn('Goal reached', trace.state_msg)
        self.assertEqual(participant.state, 'completed')
        self.assertTrue(participant.completion_date)

    def test_goal_4_no_goal_participant_stays_running(self):
        """Without a goal domain the participant keeps running."""
        partner = self._create_partner(function='cto')
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        self._schedule_now(participant.trace_ids)
        campaign.execute_activities()
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'processed')
        self.assertFalse(trace.goal_met)

    def test_goal_5_domain_without_target_field_is_safe(self):
        """A goal domain that no record matches never fires spuriously."""
        partner = self._create_partner()
        campaign = self._create_campaign(
            goal_domain="[('function','=','never')]")
        activity = self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self.assertFalse(trace.goal_met)
        self.assertEqual(participant.state, 'running')

    def test_goal_6_removing_goal_revives_pending_traces(self):
        """Clearing the goal domain leaves pending traces executable."""
        partner = self._create_partner(function='cto')
        action = self._action_server('res.partner')
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        campaign.goal_domain = False
        trace.invalidate_recordset()
        self.assertFalse(trace.goal_met)
        self._schedule_now(trace)
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'processed')
