# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestParticipant(MarketingAutomationCommon):
    """Task 4.x — participant synchronisation and lifecycle."""

    def test_4_1_participant_fields(self):
        """4.1 A participant carries campaign/model/res_id and a reference."""
        partner = self._create_partner(name='Reference Co')
        campaign = self._create_campaign()
        participant = self._create_participant(campaign, partner)
        self.assertEqual(participant.campaign_id, campaign)
        self.assertEqual(participant.model_id, self.partner_model)
        self.assertEqual(participant.model_name, 'res.partner')
        self.assertEqual(participant.res_id, partner.id)
        self.assertEqual(participant.resource_ref, partner)
        self.assertEqual(participant.state, 'running')
        self.assertFalse(participant.is_test)

    def test_4_2_resource_ref_inverse(self):
        """4.1 Writing resource_ref sets res_id."""
        campaign = self._create_campaign()
        first = self._create_partner(name='First')
        second = self._create_partner(name='Second')
        participant = self._create_participant(campaign, first)
        participant.resource_ref = second
        self.assertEqual(participant.res_id, second.id)

    def test_4_3_sync_creates_participants(self):
        """4.2 sync_participants creates one participant per matching record."""
        partners = self.env['res.partner'].create([
            {'name': 'Sync One', 'function': 'cto'},
            {'name': 'Sync Two', 'function': 'cto'},
            {'name': 'Not Matching', 'function': False},
        ])
        campaign = self._create_campaign(
            domain="[('function','=','cto')]")
        self._create_activity(campaign, name='Step 1')
        new_participants = campaign.sync_participants()
        expected = partners.filtered(lambda p: p.function == 'cto')
        self.assertEqual(set(new_participants.mapped('res_id')),
                         set(expected.ids))
        self.assertEqual(
            self.env['marketing.participant'].search_count(
                [('campaign_id', '=', campaign.id)]),
            len(expected))

    def test_4_4_sync_is_idempotent(self):
        """4.3 Running the sync twice creates no duplicates."""
        self.env['res.partner'].create([
            {'name': 'Idem One', 'function': 'cto'},
            {'name': 'Idem Two', 'function': 'cto'},
        ])
        campaign = self._create_campaign(
            domain="[('function','=','cto')]")
        self._create_activity(campaign, name='Step 1')
        campaign.sync_participants()
        count = self.env['marketing.participant'].search_count(
            [('campaign_id', '=', campaign.id)])
        second = campaign.sync_participants()
        self.assertFalse(second)
        self.assertEqual(
            self.env['marketing.participant'].search_count(
                [('campaign_id', '=', campaign.id)]), count)

    def test_4_5_sync_removes_participants(self):
        """4.4 Records that no longer match are marked removed."""
        partner = self._create_partner(function='cto')
        campaign = self._create_campaign(
            domain="[('function','=','cto')]")
        self._create_activity(campaign, name='Step 1')
        campaign.sync_participants()
        participant = self.env['marketing.participant'].search(
            [('campaign_id', '=', campaign.id),
             ('res_id', '=', partner.id)])
        self.assertEqual(participant.state, 'running')

        partner.function = 'ceo'
        campaign.sync_participants()
        participant.invalidate_recordset()
        self.assertEqual(participant.state, 'unlinked')
        # Scheduled traces were cancelled with a reason.
        self.assertTrue(participant.trace_ids)
        for trace in participant.trace_ids:
            self.assertEqual(trace.state, 'canceled')
            self.assertIn('Record deleted', trace.state_msg)

    def test_4_6_unique_field_filter(self):
        """4.5 Uniqueness filtering drops duplicates on the chosen field."""
        email_field = self.env['ir.model.fields'].search([
            ('model', '=', 'res.partner'),
            ('name', '=', 'email'),
        ], limit=1)
        self.env['res.partner'].create([
            {'name': 'Dup A', 'email': 'dup@example.com',
             'function': 'cto'},
            {'name': 'Dup B', 'email': 'dup@example.com',
             'function': 'cto'},
            {'name': 'Solo', 'email': 'solo@example.com',
             'function': 'cto'},
        ])
        campaign = self._create_campaign(
            domain="[('function','=','cto')]")
        self._create_activity(campaign, name='Step 1')
        # The compute resets the field, so set it after domain computation.
        campaign.write({'unique_field_id': email_field.id})
        campaign.sync_participants()
        participants = self.env['marketing.participant'].search(
            [('campaign_id', '=', campaign.id)])
        emails = [self.env['res.partner'].browse(p.res_id).email
                  for p in participants]
        self.assertEqual(sorted(emails),
                         ['dup@example.com', 'solo@example.com'])

    def test_4_7_reenrollment_never(self):
        """4.6 'never' blocks a completed record from re-entering."""
        partner = self._create_partner(function='cto')
        campaign = self._create_campaign(
            domain="[('function','=','cto')]",
            reenrollment_policy='never')
        self._create_activity(campaign, name='Step 1')
        campaign.sync_participants()
        participant = self.env['marketing.participant'].search(
            [('campaign_id', '=', campaign.id)])
        participant.write({'state': 'completed'})
        self.assertFalse(campaign.sync_participants())
        self.assertEqual(
            self.env['marketing.participant'].search_count(
                [('campaign_id', '=', campaign.id)]), 1)
        self.assertEqual(participant.res_id, partner.id)

    def test_4_8_reenrollment_after_delay(self):
        """4.6 'after_delay' lets a record in once the delay has passed."""
        partner = self._create_partner(function='cto')
        campaign = self._create_campaign(
            domain="[('function','=','cto')]",
            reenrollment_policy='after_delay',
            reenrollment_delay=5, reenrollment_delay_type='days')
        self._create_activity(campaign, name='Step 1')
        campaign.sync_participants()
        participant = self.env['marketing.participant'].search(
            [('campaign_id', '=', campaign.id)])
        participant.write({
            'state': 'completed',
            'completion_date': fields.Datetime.now() - relativedelta(days=6),
        })
        # The old participant is replaced by a fresh one.
        new_participants = campaign.sync_participants()
        self.assertTrue(new_participants)
        self.assertEqual(new_participants.mapped('res_id'), partner.ids)
        self.assertNotEqual(new_participants, participant)

    def test_4_9_root_trace_created(self):
        """4.7 A new participant gets one trace per 'begin' activity."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        begin_one = self._create_activity(campaign, name='Begin 1')
        begin_two = self._create_activity(campaign, name='Begin 2')
        self._create_activity(
            campaign, name='Not begin', trigger_type='activity',
            parent_id=begin_one.id)
        participant = self._create_participant(campaign, partner)
        self.assertEqual(len(participant.trace_ids), 2)
        self.assertEqual(set(participant.trace_ids.mapped('activity_id').ids),
                         {begin_one.id, begin_two.id})
        for trace in participant.trace_ids:
            self.assertEqual(trace.state, 'scheduled')
            self.assertTrue(trace.schedule_date)
            self.assertFalse(trace.parent_id)

    def test_4_10_check_completed(self):
        """4.8 A participant with no scheduled trace becomes completed."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        participant.trace_ids.action_cancel(message='done')
        participant.invalidate_recordset()
        # Cancelling the last scheduled trace completes the participant.
        self.assertEqual(participant.state, 'completed')
        self.assertTrue(participant.completion_date)

    def test_4_11_action_set_completed_cancels_traces(self):
        """4.9 Marking a participant completed cancels every pending trace."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        self._create_activity(campaign, name='Step')
        participant = self._create_participant(campaign, partner)
        participant.action_set_completed()
        self.assertEqual(participant.state, 'completed')
        for trace in participant.trace_ids:
            self.assertEqual(trace.state, 'canceled')
            self.assertIn('Marked as completed', trace.state_msg)

    def test_4_12_campaign_domain_switch(self):
        """4.10 Switching the target model warns about existing activities."""
        campaign = self._create_campaign()
        self._create_activity(campaign)
        warning = campaign._onchange_model_id()
        self.assertIn('warning', warning)

    def test_4_13_sync_sets_last_sync_date(self):
        """4.11 The first sync records last_sync_date."""
        self._create_partner(function='cto')
        campaign = self._create_campaign(
            domain="[('function','=','cto')]")
        self._create_activity(campaign, name='Step 1')
        self.assertFalse(campaign.last_sync_date)
        campaign.sync_participants()
        self.assertTrue(campaign.last_sync_date)
