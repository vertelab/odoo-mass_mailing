# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from ast import literal_eval

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestCampaignModel(MarketingAutomationCommon):
    """Task 3.x — the campaign record and its datamodel."""

    def test_3_1_module_installed(self):
        """3.1 The module is installable and its models are registered."""
        module = self.env['ir.module.module'].search(
            [('name', '=', 'marketing_automation_ce')], limit=1)
        self.assertEqual(module.state, 'installed')
        self.assertEqual(module.license, 'AGPL-3')
        for model in ('marketing.campaign', 'marketing.activity',
                      'marketing.participant', 'marketing.trace'):
            self.assertIn(model, self.env)

    def test_3_2_campaign_inherits_utm_campaign(self):
        """3.2 The campaign is an utm.campaign (title/name/stage from utm)."""
        campaign = self._create_campaign(title='Spring Launch')
        self.assertTrue(campaign.utm_campaign_id)
        self.assertEqual(campaign.title, 'Spring Launch')
        self.assertEqual(campaign.utm_campaign_id.name, 'Spring Launch')
        self.assertTrue(campaign.stage_id)

    def test_3_3_campaign_defaults(self):
        """3.3 A new campaign starts in draft, is active and is an auto one."""
        campaign = self._create_campaign()
        self.assertEqual(campaign.state, 'draft')
        self.assertTrue(campaign.active)
        self.assertTrue(campaign.utm_campaign_id.is_auto_campaign)
        self.assertEqual(campaign.model_name, 'res.partner')
        self.assertEqual(campaign.domain, '[]')

    def test_3_4_reenrollment_delay_constraint(self):
        """3.4 'After a delay' requires a delay greater than zero."""
        with self.assertRaises(ValidationError):
            self._create_campaign(
                reenrollment_policy='after_delay', reenrollment_delay=0)
        # A positive delay is accepted.
        campaign = self._create_campaign(
            reenrollment_policy='after_delay', reenrollment_delay=3)
        self.assertEqual(campaign.reenrollment_delay, 3)

    def test_3_5_goal_domain_validation(self):
        """3.5 The goal domain must be a list literal."""
        with self.assertRaises(ValidationError):
            self._create_campaign(goal_domain="['not a domain'")
        with self.assertRaises(ValidationError):
            self._create_campaign(goal_domain="'a string'")
        campaign = self._create_campaign(goal_domain="[('function','=','cto')]")
        self.assertEqual(campaign.goal_domain, "[('function','=','cto')]")

    def test_3_6_goal_met_is_stored(self):
        """3.6 goal_met is a stored compute on the trace."""
        field = self.env['marketing.trace']._fields['goal_met']
        self.assertTrue(field.store)
        self.assertTrue(field.compute)
        self.assertEqual(field.compute, '_compute_goal_met')

    def test_3_7_goal_met_evaluates_domain(self):
        """3.6/3.7 goal_met follows the participant's record."""
        partner = self._create_partner(function='cto')
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        activity = self._create_activity(campaign, name='Step 1')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self.assertTrue(trace)
        self.assertTrue(trace.goal_met)

        partner.write({'function': False})
        campaign._recompute_goals()
        trace.invalidate_recordset()
        self.assertFalse(trace.goal_met)

    def test_3_8_goal_met_without_domain(self):
        """3.6 No goal domain means the goal is never met."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        activity = self._create_activity(campaign, name='Step 1')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self.assertFalse(trace.goal_met)

    def test_3_9_activity_constraints(self):
        """3.9/3.10 Activity constraints: payload, cycle and condition step."""
        campaign = self._create_campaign()
        # Email step requires a mailing.
        with self.assertRaises(ValidationError):
            self._create_activity(campaign, activity_type='email')
        # Server action step requires a server action.
        with self.assertRaises(ValidationError):
            self.env['marketing.activity'].create({
                'name': 'No action',
                'campaign_id': campaign.id,
                'activity_type': 'action',
                'trigger_type': 'begin',
            })
        # Condition step that waits requires a timeout.
        with self.assertRaises(ValidationError):
            self._create_activity(
                campaign, activity_type='condition', condition_wait=True,
                condition_timeout=0)

    def test_3_11_activity_parent_consistency(self):
        """3.10 A mail-reaction trigger requires an email parent."""
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        parent = self._create_activity(
            campaign, name='Action', activity_type='action',
            server_action_id=action.id)
        with self.assertRaises(ValidationError):
            self._create_activity(
                campaign, name='Opened?', activity_type='action',
                server_action_id=action.id, trigger_type='mail_not_open',
                parent_id=parent.id)

    def test_3_12_activity_inherited_domain(self):
        """3.11 The inherited domain ANDs campaign, parents and own domain."""
        campaign = self._create_campaign(domain="[('active','=',True)]")
        action = self._action_server('res.partner')
        parent = self._create_activity(
            campaign, name='Parent', activity_type='action',
            server_action_id=action.id,
            activity_domain="[('function','=','cto')]")
        child = self._create_activity(
            campaign, name='Child', activity_type='action',
            server_action_id=action.id, trigger_type='activity',
            parent_id=parent.id,
            activity_domain="[('is_company','=',True)]")
        # ``domain`` is a Char holding the ANDed, repr'd domain.
        applied = literal_eval(child.domain)
        self.assertIn(('active', '=', True), applied)
        self.assertIn(('function', '=', 'cto'), applied)
        self.assertIn(('is_company', '=', True), applied)

    def test_3_13_activity_interval_standardized(self):
        """3.12 interval_standardized is stored in hours."""
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            interval_number=2, interval_type='days')
        self.assertEqual(activity.interval_standardized, 48)

    def test_3_14_campaign_copy_remaps_parents(self):
        """3.13 Copying a campaign copies the tree and remaps parent_id."""
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        parent = self._create_activity(
            campaign, name='Parent', activity_type='action',
            server_action_id=action.id)
        self._create_activity(
            campaign, name='Child', activity_type='action',
            server_action_id=action.id, trigger_type='activity',
            parent_id=parent.id)
        copy = campaign.copy()
        self.assertNotEqual(copy, campaign)
        self.assertEqual(len(copy.marketing_activity_ids), 2)
        new_child = copy.marketing_activity_ids.filtered(
            lambda a: a.name == 'Child')
        new_parent = copy.marketing_activity_ids.filtered(
            lambda a: a.name == 'Parent')
        self.assertEqual(new_child.parent_id, new_parent)
        self.assertNotEqual(new_parent, parent)
        self.assertFalse(copy.participant_ids)
        self.assertFalse(copy.last_sync_date)

    def test_3_15_campaign_state_flow(self):
        """3.14 Start requires an activity; stop and restart are reversible."""
        campaign = self._create_campaign()
        with self.assertRaises(ValidationError):
            campaign.action_start_campaign()
        action = self._action_server('res.partner')
        self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        campaign.action_start_campaign()
        self.assertEqual(campaign.state, 'running')
        campaign.action_stop_campaign()
        self.assertEqual(campaign.state, 'stopped')
        campaign.action_start_campaign()
        self.assertEqual(campaign.state, 'running')

    def test_3_16_archiving_stops_the_campaign(self):
        """3.15 Archiving a campaign also stops it."""
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        campaign.action_start_campaign()
        campaign.write({'active': False})
        self.assertEqual(campaign.state, 'stopped')

    def test_3_17_campaign_counts(self):
        """3.16 Participant counters split running/completed/test."""
        partner_a = self._create_partner(name='A')
        partner_b = self._create_partner(name='B')
        partner_t = self._create_partner(name='T')
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        self._create_participant(campaign, partner_a)
        done = self._create_participant(campaign, partner_b)
        done.write({'state': 'completed'})
        self._create_participant(campaign, partner_t, is_test=True)
        campaign.invalidate_recordset()
        self.assertEqual(campaign.running_participant_count, 1)
        self.assertEqual(campaign.completed_participant_count, 1)
        self.assertEqual(campaign.total_participant_count, 2)
        self.assertEqual(campaign.test_participant_count, 1)

    def test_3_18_reenrollment_policies(self):
        """3.17 _reenrollment_allows implements never/once/after_delay."""
        partner = self._create_partner()
        campaign = self._create_campaign(reenrollment_policy='never')
        self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        # 'never': nobody re-enters, completed or not.
        self.assertFalse(campaign._reenrollment_allows(
            campaign, partner.id, participant))

        # 'once': allowed while still running, blocked once completed.
        campaign.reenrollment_policy = 'once'
        self.assertTrue(campaign._reenrollment_allows(
            campaign, partner.id, participant))
        participant.write({'state': 'completed'})
        self.assertFalse(campaign._reenrollment_allows(
            campaign, partner.id, participant))

        # 'after_delay': allowed only once the delay has passed.
        campaign.write({
            'reenrollment_policy': 'after_delay',
            'reenrollment_delay': 5,
            'reenrollment_delay_type': 'days',
        })
        participant.write({
            'completion_date': fields.Datetime.now() - relativedelta(days=1),
        })
        self.assertFalse(campaign._reenrollment_allows(
            campaign, partner.id, participant))
        participant.write({
            'completion_date': fields.Datetime.now() - relativedelta(days=6),
        })
        self.assertTrue(campaign._reenrollment_allows(
            campaign, partner.id, participant))
