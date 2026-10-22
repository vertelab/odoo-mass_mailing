# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestActivityModel(MarketingAutomationCommon):
    """Task 8.x — activity datamodel and configuration helpers."""

    def test_8_1_activity_types(self):
        """8.1 The three activity types are email, action and condition."""
        selection = dict(self.env['marketing.activity']._fields[
            'activity_type'].selection)
        self.assertEqual(set(selection), {'email', 'action', 'condition'})

    def test_8_2_trigger_types(self):
        """8.2 Every trigger type in the specification exists."""
        selection = dict(self.env['marketing.activity']._fields[
            'trigger_type'].selection)
        for trigger in ('begin', 'activity', 'mail_open', 'mail_not_open',
                        'mail_click', 'mail_not_click', 'mail_reply',
                        'mail_not_reply', 'mail_bounce'):
            self.assertIn(trigger, selection)
        self.assertEqual(selection['begin'], 'beginning of workflow')

    def test_8_3_reschedule_trigger_types(self):
        """8.2 Only the documented triggers reschedule from the parent."""
        types = self.env['marketing.activity']._get_reschedule_trigger_types()
        self.assertEqual(set(types), {
            'begin', 'activity', 'mail_not_open', 'mail_not_click',
            'mail_not_reply'})

    def test_8_4_interval_standardized_months(self):
        """8.3 month = 720 hours in the standardised interval."""
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            interval_number=1, interval_type='months')
        self.assertEqual(activity.interval_standardized, 720)
        activity.write({'interval_type': 'weeks', 'interval_number': 2})
        self.assertEqual(activity.interval_standardized, 336)

    def test_8_5_activity_order(self):
        """8.3 Activities are ordered by standardised interval, then id."""
        self.assertEqual(self.env['marketing.activity']._order,
                         'interval_standardized, id ASC')

    def test_8_6_utm_source_mixin(self):
        """8.4 Every activity carries a utm source.

        ``utm.source.mixin`` creates the source on ``create()`` and derives
        its name from ``_rec_name`` — the activity name.
        """
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        activity = self._create_activity(
            campaign, name='Welcome mail', activity_type='action',
            server_action_id=action.id)
        self.assertTrue(activity.source_id)
        self.assertIn('Welcome mail', activity.source_id.name)

    def test_8_7_stored_computes_are_writable(self):
        """8.5 mass_mailing_id and server_action_id are writable computes."""
        for name in ('mass_mailing_id', 'server_action_id'):
            field = self.env['marketing.activity']._fields[name]
            self.assertTrue(field.store, "%s must be stored" % name)
            self.assertFalse(field.readonly, "%s must be writable" % name)

    def test_8_8_parent_defaults_to_begin(self):
        """8.6 A step without a parent is a 'begin' step."""
        campaign = self._create_campaign()
        activity = self._create_activity(campaign, name='Begin')
        self.assertFalse(activity.parent_id)
        self.assertEqual(activity.trigger_type, 'begin')
        self.assertFalse(activity.trigger_category)

    def test_8_9_allowed_parent_ids(self):
        """8.6 The candidate parents depend on the trigger and the type.

        An ``activity``-triggered step may hang off any sibling; a
        mail-triggered step may only hang off steps of the same category
        (mail steps); a ``begin`` step has no candidates. The step itself is
        never its own candidate.
        """
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        first = self._create_activity(
            campaign, name='First', activity_type='action',
            server_action_id=action.id, interval_number=1)
        second = self._create_activity(
            campaign, name='Second', activity_type='action',
            server_action_id=action.id, interval_number=5)
        # A begin step can never pick a parent.
        self.assertFalse(first.allowed_parent_ids)
        # An activity-triggered step sees every sibling, never itself.
        second.write({'trigger_type': 'activity', 'parent_id': first.id})
        self.assertIn(first, second.allowed_parent_ids)
        self.assertNotIn(second, second.allowed_parent_ids)
        # A mail-triggered step only sees steps of the mail category.
        second.write({'trigger_type': 'mail_reply', 'parent_id': False})
        self.assertFalse(second.allowed_parent_ids)

    def test_8_10_trigger_category(self):
        """8.6 The trigger category groups triggers for the UI."""
        campaign = self._create_campaign()
        action = self._action_server('res.partner')
        begin = self._create_activity(
            campaign, name='Begin', activity_type='action',
            server_action_id=action.id)
        self.assertFalse(begin.trigger_category)
        child = self._create_activity(
            campaign, name='Child', activity_type='action',
            server_action_id=action.id, trigger_type='activity',
            parent_id=begin.id)
        self.assertFalse(child.trigger_category)
        # A mail-reaction trigger needs an email step as its parent.
        mailing = self.env['mailing.mailing'].create({
            'name': 'Category mailing',
            'subject': 'Subject',
            'mailing_model_id': self.partner_model_id,
            'mailing_domain': "[]",
            'body_html': '<p>Hello</p>',
        })
        email = self._create_activity(
            campaign, name='Email', activity_type='email',
            mass_mailing_id=mailing.id)
        replied = self._create_activity(
            campaign, name='Replied', activity_type='action',
            server_action_id=action.id, trigger_type='mail_reply',
            parent_id=email.id)
        self.assertEqual(replied.trigger_category, 'email')

    def test_8_11_start_without_activity_raises(self):
        """8.7 A campaign cannot start without at least one activity."""
        campaign = self._create_campaign()
        with self.assertRaises(ValidationError) as ctx:
            campaign.action_start_campaign()
        self.assertIn('at least one activity', str(ctx.exception))

    def test_8_12_sync_requires_setup(self):
        """8.7 action_set_synchronized requires a running campaign."""
        campaign = self._create_campaign()
        self.assertFalse(campaign.require_sync)

    def test_8_13_deleting_mailing_used_by_activity_is_blocked(self):
        """8.8 A mailing used by an activity cannot be deleted."""
        mailing_model = self.env['ir.model']._get('res.partner')
        mailing = self.env['mailing.mailing'].create({
            'name': 'Guarded',
            'subject': 'Subject',
            'mailing_model_id': mailing_model.id,
            'mailing_domain': "[]",
            'body_html': '<p>x</p>',
            'use_in_marketing_automation': True,
        })
        campaign = self._create_campaign()
        self._create_activity(
            campaign, activity_type='email', mass_mailing_id=mailing.id)
        with self.assertRaises(Exception):
            mailing.unlink()

    def test_8_14_form_creates_condition(self):
        """8.9 A condition step can be created from the form view."""
        campaign = self._create_campaign()
        with Form(self.env['marketing.activity']) as form:
            form.campaign_id = campaign
            form.name = 'Condition from form'
            form.activity_type = 'condition'
            form.condition_domain = "[('function','=','cto')]"
        activity = form.record
        self.assertEqual(activity.activity_type, 'condition')
        self.assertEqual(activity.campaign_id, campaign)
