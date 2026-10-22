# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields
from odoo.tests import tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestEvents(MarketingAutomationCommon):
    """Task 9.x — statistics, counts and the documents drill-down."""

    def _mailing_campaign(self, partner):
        mailing_model = self.env['ir.model']._get('res.partner')
        mailing = self.env['mailing.mailing'].create({
            'name': 'Stats mailing',
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
        participant = self._create_participant(campaign, partner)
        email_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == email)
        mailing_trace = self.env['mailing.trace'].create({
            'model': 'res.partner',
            'res_id': partner.id,
            'mass_mailing_id': mailing.id,
            'marketing_trace_id': email_trace.id,
            'trace_type': 'mail',
            'email': partner.email or 'stats@example.com',
        })
        return campaign, email, email_trace, mailing_trace, participant

    def test_9_1_statistics_counters(self):
        """9.1 Sent/replied/opened/bounced counters read the mailing traces."""
        partner = self._create_partner(email='stats@example.com')
        campaign, email, email_trace, mailing_trace, participant = \
            self._mailing_campaign(partner)
        email_trace.write({'state': 'processed'})
        mailing_trace.set_sent()
        mailing_trace.set_opened()
        mailing_trace.set_replied()
        email.invalidate_recordset()
        self.assertGreaterEqual(email.total_sent, 1)
        self.assertGreaterEqual(email.total_open, 1)
        self.assertGreaterEqual(email.total_reply, 1)

    def test_9_2_bounce_counter(self):
        """9.2 Bounces are counted separately."""
        partner = self._create_partner(email='bounce-stats@example.com')
        campaign, email, email_trace, mailing_trace, participant = \
            self._mailing_campaign(partner)
        email_trace.write({'state': 'error'})
        mailing_trace.set_bounced()
        email.invalidate_recordset()
        self.assertGreaterEqual(email.total_bounce, 1)

    def test_9_3_test_participants_excluded(self):
        """9.3 Test participants are excluded from statistics."""
        partner = self._create_partner(email='excluded@example.com')
        campaign, email, email_trace, mailing_trace, participant = \
            self._mailing_campaign(partner)
        participant.write({'is_test': True})
        email_trace.write({'state': 'processed'})
        mailing_trace.set_opened()
        email.invalidate_recordset()
        self.assertEqual(email.total_sent, 0)
        self.assertEqual(email.total_open, 0)

    def test_9_4_graph_statistics(self):
        """9.4 The graph data has a success and a rejected series."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        self._schedule_now(participant.trace_ids)
        campaign.execute_activities()
        graph = activity._get_graph_statistics()
        self.assertIn(activity._origin.id, graph)
        labels = [series['label'] for series in graph[activity._origin.id]]
        self.assertIn('Success', labels)
        self.assertIn('Rejected', labels)

    def test_9_5_view_sent_documents(self):
        """9.5 The drill-down opens the participants of the activity."""
        partner = self._create_partner(email='drill@example.com')
        campaign, email, email_trace, mailing_trace, participant = \
            self._mailing_campaign(partner)
        email_trace.write({'state': 'processed'})
        mailing_trace.write({'sent_datetime': fields.Datetime.now()})
        action = email.action_view_sent()
        self.assertTrue(action)
        self.assertEqual(action['res_model'], 'marketing.participant')
        domain = action['domain']
        self.assertEqual(domain[0][0], 'id')
        self.assertEqual(domain[0][1], 'in')
        self.assertIn(participant.id, domain[0][2])
        # An activity without a mailing has no drill-down.
        plain = self._create_activity(campaign, name='Plain')
        self.assertFalse(plain.action_view_sent())

    def test_9_6_campaign_test_participant_count(self):
        """9.6 Test participants are counted on the campaign."""
        partner = self._create_partner()
        campaign = self._create_campaign()
        self._create_activity(campaign, name='Step')
        self._create_participant(campaign, partner, is_test=True)
        campaign.invalidate_recordset()
        self.assertEqual(campaign.test_participant_count, 1)
        self.assertEqual(campaign.total_participant_count, 0)

    def test_9_7_use_in_marketing_automation_default(self):
        """9.7 Mailings default to NOT being automation mailings."""
        mailing = self.env['mailing.mailing'].create({
            'name': 'Plain mailing',
            'subject': 'Subject',
            'mailing_model_id':
                self.env['ir.model']._get('res.partner').id,
            'mailing_domain': "[]",
            'body_html': '<p>x</p>',
        })
        self.assertFalse(mailing.use_in_marketing_automation)

    def test_9_8_seen_list_excludes_test_traces(self):
        """9.8 Test traces never exclude a contact from a real mailing."""
        partner = self._create_partner(email='seen@example.com')
        campaign, email, email_trace, mailing_trace, participant = \
            self._mailing_campaign(partner)
        mailing = email.mass_mailing_id
        # A real (non-test) trace whose email is the same gets seen.
        self.assertIn(partner.email, mailing._get_seen_list())
        # Turning the participant into a test record removes it again.
        participant.write({'is_test': True})
        self.env['marketing.trace'].flush_model(['is_test'])
        self.assertNotIn(partner.email, mailing._get_seen_list())
