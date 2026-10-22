# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from .common import MarketingAutomationCommon


@tagged('post_install', '-at_install')
class TestExecution(MarketingAutomationCommon):
    """Tasks 5.x and 7.x — execution, scheduling and server actions."""

    def _tag_code(self, tag):
        """A server action that stamps the partner's name with a tag."""
        return (
            "for rec in records:\n"
            "    rec.write({'name': '%s'})\n" % tag
        )

    def test_5_1_execute_only_due_traces(self):
        """5.1 Only traces whose schedule_date has passed are executed."""
        partner = self._create_partner()
        action = self._action_server(
            'res.partner', code=self._tag_code('ran'))
        campaign = self._create_campaign()
        # A non-zero interval puts the first run in the future.
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            interval_number=2, interval_type='days')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        # Not due yet.
        self.assertGreater(trace.schedule_date, fields.Datetime.now())
        self.assertEqual(trace.state, 'scheduled')
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'scheduled')

        self._schedule_now(trace)
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'processed')
        self.assertEqual(partner.name, 'ran')

    def test_5_2_execute_skips_stopped_participant(self):
        """5.2 A participant that is no longer running is not executed."""
        partner = self._create_partner()
        action = self._action_server(
            'res.partner', code=self._tag_code('ran'))
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        participant.action_set_completed()
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        trace.write({'state': 'scheduled',
                     'schedule_date': fields.Datetime.now()
                     - relativedelta(minutes=1)})
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'scheduled')
        self.assertNotEqual(partner.name, 'ran')

    def test_5_3_cron_records(self):
        """5.3 The two ir.cron records exist and are active."""
        sync = self.env.ref(
            'marketing_automation_ce.ir_cron_campaign_sync_participants',
            raise_if_not_found=False)
        run = self.env.ref(
            'marketing_automation_ce.ir_cron_campaign_execute_activities',
            raise_if_not_found=False)
        self.assertTrue(sync, "Sync cron record missing")
        self.assertTrue(run, "Run cron record missing")
        self.assertTrue(sync.active)
        self.assertTrue(run.active)
        self.assertEqual(sync.model_id.model, 'marketing.campaign')
        self.assertEqual(run.model_id.model, 'marketing.campaign')
        self.assertIn('sync_participants', sync.code)
        self.assertIn('execute_activities', run.code)

    def test_5_4_validity_window_cancels_expired(self):
        """5.4 A trace older than the validity window is cancelled."""
        partner = self._create_partner()
        action = self._action_server('res.partner')
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            validity_duration=True, validity_duration_number=2,
            validity_duration_type='days')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self._schedule_now(
            trace,
            schedule_date=fields.Datetime.now() - relativedelta(days=5))
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'canceled')
        self.assertIn('Expired', trace.state_msg)

    def test_5_5_validity_window_keeps_fresh(self):
        """5.4 A trace inside the validity window still runs."""
        partner = self._create_partner()
        action = self._action_server('res.partner')
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            validity_duration=True, validity_duration_number=2,
            validity_duration_type='days')
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self._schedule_now(trace)  # one minute ago, inside 2 days
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'processed')

    def test_5_6_goal_met_skips_activity(self):
        """5.6 A participant that met the goal is not sent the activity."""
        partner = self._create_partner(function=False)
        action = self._action_server(
            'res.partner', code=self._tag_code('ran'))
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        # The record converts before the step runs.
        partner.write({'function': 'cto', 'name': 'converted'})
        trace.invalidate_recordset()
        self.assertTrue(trace.goal_met)
        self._schedule_now(trace)
        campaign.execute_activities()
        trace.invalidate_recordset()
        # The payload did not run…
        self.assertEqual(trace.state, 'canceled')
        self.assertIn('Goal reached', trace.state_msg)
        self.assertEqual(partner.name, 'converted')
        # …and the participant's flow ended.
        self.assertEqual(participant.state, 'completed')

    def test_5_7_goal_not_met_runs_activity(self):
        """5.6 Without goal match the activity runs normally."""
        partner = self._create_partner(function=False)
        action = self._action_server(
            'res.partner', code=self._tag_code('ran'))
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self._schedule_now(trace)
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'processed')
        self.assertEqual(partner.name, 'ran')

    def test_5_8_goal_skip_keeps_other_participants(self):
        """5.6 Only the participant that met the goal is skipped."""
        converted = self._create_partner(name='converted', function='cto')
        pending = self._create_partner(name='pending', function=False)
        done_tag = self._action_server(
            'res.partner', name='tag', code=(
                "for rec in records:\n"
                "    rec.write({'name': rec.name + ' ran'})\n"))
        campaign = self._create_campaign(
            goal_domain="[('function','=','cto')]")
        self._create_activity(
            campaign, activity_type='action', server_action_id=done_tag.id)
        p1 = self._create_participant(campaign, converted)
        p2 = self._create_participant(campaign, pending)
        self._schedule_now(p1.trace_ids | p2.trace_ids)
        campaign.execute_activities()
        p1.invalidate_recordset()
        p2.invalidate_recordset()
        # The converted participant was skipped: the goal trace is cancelled
        # and the participant is completed without the action ever running.
        self.assertEqual(p1.state, 'completed')
        self.assertEqual(converted.name, 'converted')
        self.assertTrue(p1.trace_ids.filtered(
            lambda t: t.state_msg == 'Goal reached'))
        # The pending participant ran the step, and having no scheduled
        # trace left it too is completed — but the action DID run.
        self.assertEqual(pending.name, 'pending ran')

    def test_5_9_cron_latency_documented(self):
        """5.8 The run cron interval is one hour (documented latency)."""
        run = self.env.ref(
            'marketing_automation_ce.ir_cron_campaign_execute_activities')
        self.assertEqual(run.interval_type, 'hours')
        self.assertEqual(run.interval_number, 1)

    # ── 7.x — branches, events and server actions ───────────────────────

    def test_7_1_server_action_executes(self):
        """7.1 A server action step runs in the participant's context."""
        partner = self._create_partner()
        action = self._action_server('res.partner', code=(
            "for rec in records:\n"
            "    rec.write({'name': 'from action: %s' % rec.id})\n"))
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id)
        participant = self._create_participant(campaign, partner)
        self._schedule_now(participant.trace_ids)
        campaign.execute_activities()
        self.assertEqual(partner.name, 'from action: %s' % partner.id)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self.assertEqual(trace.state, 'processed')

    def test_7_2_domain_rejection(self):
        """7.2 A trace whose record falls outside the domain is rejected."""
        partner = self._create_partner(function=False)
        action = self._action_server('res.partner')
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='action', server_action_id=action.id,
            activity_domain="[('function','=','cfo')]")
        participant = self._create_participant(campaign, partner)
        trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == activity)
        self._schedule_now(trace)
        campaign.execute_activities()
        trace.invalidate_recordset()
        self.assertEqual(trace.state, 'rejected')
        self.assertIn('Rejected', trace.state_msg)

    def test_7_3_children_traces_scheduled(self):
        """7.3 A processed step schedules its time-dependent children."""
        partner = self._create_partner()
        action = self._action_server('res.partner')
        campaign = self._create_campaign()
        parent = self._create_activity(
            campaign, name='Parent', activity_type='action',
            server_action_id=action.id, interval_number=1,
            interval_type='days')
        child = self._create_activity(
            campaign, name='Child', activity_type='action',
            server_action_id=action.id, trigger_type='activity',
            parent_id=parent.id, interval_number=3, interval_type='hours')
        participant = self._create_participant(campaign, partner)
        parent_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == parent)
        self._schedule_now(parent_trace)
        # The child's offset is computed from the parent's schedule date as
        # it stands BEFORE the parent executes (execution rewrites it to
        # "now"), so remember that value first.
        parent_schedule = parent_trace.schedule_date
        campaign.execute_activities()
        child_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == child)
        self.assertTrue(child_trace)
        self.assertEqual(child_trace.parent_id, parent_trace)
        self.assertEqual(child_trace.state, 'scheduled')
        # Three hours after the parent's (pre-execution) schedule date.
        expected = parent_schedule + relativedelta(hours=3)
        self.assertAlmostEqual(
            child_trace.schedule_date, expected, delta=timedelta(seconds=5))

    def _condition_with_branches(self, partner, condition_domain,
                                 interval_number=1, extra=None):
        """A condition with a true and a false step on separate branches."""
        action = self._action_server('res.partner')
        campaign = self._create_campaign()
        vals = {
            'name': 'Condition',
            'activity_type': 'condition',
            'condition_domain': condition_domain,
        }
        vals.update(extra or {})
        condition = self._create_activity(campaign, **vals)
        # A branch step carries the branch pointer and is triggered by an
        # activity; leaving trigger_type at 'begin' would give it its own
        # unconditional trace at participant creation.
        true_step = self._create_activity(
            campaign, name='True', activity_type='action',
            server_action_id=action.id, trigger_type='activity',
            parent_id=condition.id, interval_number=interval_number,
            condition_true_parent_id=condition.id)
        false_step = self._create_activity(
            campaign, name='False', activity_type='action',
            server_action_id=action.id, trigger_type='activity',
            parent_id=condition.id, interval_number=interval_number,
            condition_false_parent_id=condition.id)
        participant = self._create_participant(campaign, partner)
        condition_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == condition)
        return campaign, condition, true_step, false_step, participant, \
            condition_trace

    def test_7_4_condition_true_branch(self):
        """7.4 A condition routes to the true branch when it matches."""
        partner = self._create_partner(function='cto')
        (campaign, condition, true_step, false_step, participant,
         condition_trace) = self._condition_with_branches(
            partner, "[('function','=','cto')]")
        self._schedule_now(condition_trace)
        campaign.execute_activities()
        condition_trace.invalidate_recordset()
        participant.invalidate_recordset()
        self.assertEqual(condition_trace.state, 'processed')
        self.assertIn('Condition matched', condition_trace.state_msg)
        true_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == true_step)
        self.assertTrue(true_trace)
        self.assertEqual(true_trace.state, 'scheduled')
        # The branch not taken has no live trace for this participant.
        self.assertFalse(participant.trace_ids.filtered(
            lambda t: t.activity_id == false_step))

    def test_7_5_condition_false_branch(self):
        """7.5 A condition that does not match takes the false branch."""
        partner = self._create_partner(function=False)
        (campaign, condition, true_step, false_step, participant,
         condition_trace) = self._condition_with_branches(
            partner, "[('function','=','cto')]")
        self._schedule_now(condition_trace)
        campaign.execute_activities()
        condition_trace.invalidate_recordset()
        participant.invalidate_recordset()
        self.assertIn('Condition not matched', condition_trace.state_msg)
        self.assertFalse(participant.trace_ids.filtered(
            lambda t: t.activity_id == true_step))
        false_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == false_step)
        self.assertTrue(false_trace)
        self.assertEqual(false_trace.state, 'scheduled')

    def test_7_6_condition_wait_reschedules(self):
        """7.6 A waiting condition reschedules itself until the timeout."""
        partner = self._create_partner(function=False)
        (campaign, condition, true_step, false_step, participant,
         condition_trace) = self._condition_with_branches(
            partner, "[('function','=','cto')]",
            extra={'condition_wait': True, 'condition_timeout': 2,
                   'condition_timeout_type': 'days'})
        self._schedule_now(condition_trace)
        campaign.execute_activities()
        condition_trace.invalidate_recordset()
        participant.invalidate_recordset()
        # Still scheduled — waiting for the condition to become true.
        self.assertEqual(condition_trace.state, 'scheduled')
        self.assertFalse(participant.trace_ids.filtered(
            lambda t: t.activity_id == false_step))
        self.assertEqual(participant.state, 'running')
        # The deadline is rolled forward so the wait can expire.
        self.assertGreaterEqual(
            condition_trace.schedule_date, fields.Datetime.now()
            - relativedelta(minutes=1))

    def test_7_7_condition_wait_timeout_falls_through(self):
        """7.6 Past the timeout the false branch is taken."""
        partner = self._create_partner(function=False)
        (campaign, condition, true_step, false_step, participant,
         condition_trace) = self._condition_with_branches(
            partner, "[('function','=','cto')]",
            extra={'condition_wait': True, 'condition_timeout': 1,
                   'condition_timeout_type': 'days'})
        # Scheduled two days ago — the one-day timeout has passed.
        self._schedule_now(
            condition_trace,
            schedule_date=fields.Datetime.now() - relativedelta(days=2))
        campaign.execute_activities()
        condition_trace.invalidate_recordset()
        self.assertEqual(condition_trace.state, 'processed')
        self.assertTrue(participant.trace_ids.filtered(
            lambda t: t.activity_id == false_step))

    def test_7_8_condition_met_after_wait(self):
        """7.6 A met condition takes the true branch while waiting."""
        partner = self._create_partner(function=False)
        (campaign, condition, true_step, false_step, participant,
         condition_trace) = self._condition_with_branches(
            partner, "[('function','=','cto')]",
            extra={'condition_wait': True, 'condition_timeout': 5,
                   'condition_timeout_type': 'days'})
        self._schedule_now(condition_trace)
        campaign.execute_activities()
        condition_trace.invalidate_recordset()
        self.assertEqual(condition_trace.state, 'scheduled')
        # The condition becomes true on the next pass.
        partner.function = 'cto'
        self._schedule_now(condition_trace)
        campaign.execute_activities()
        condition_trace.invalidate_recordset()
        self.assertEqual(condition_trace.state, 'processed')
        self.assertTrue(participant.trace_ids.filtered(
            lambda t: t.activity_id == true_step))

    def test_7_9_other_branch_cancelled(self):
        """7.7 Taking one branch cancels the traces of the other one."""
        partner = self._create_partner(function=False)
        (campaign, condition, true_step, false_step, participant,
         condition_trace) = self._condition_with_branches(
            partner, "[('function','=','cto')]")
        self._schedule_now(condition_trace)
        campaign.execute_activities()
        participant.invalidate_recordset()
        # The false branch was taken; the true branch is cancelled.
        false_trace = participant.trace_ids.filtered(
            lambda t: t.activity_id == false_step)
        self.assertTrue(false_trace)
        false_trace.invalidate_recordset()
        self.assertEqual(false_trace.state, 'scheduled')
        # No live trace exists on the branch that was not taken.
        participant.invalidate_recordset()
        self.assertFalse(participant.trace_ids.filtered(
            lambda t: t.activity_id == true_step
            and t.state == 'scheduled'))

    def test_7_10_email_step_uses_the_mailing(self):
        """7.8 An email step is driven by its linked mailing."""
        mailing_model = self.env['ir.model']._get('res.partner')
        mailing = self.env['mailing.mailing'].create({
            'name': 'Linkage mailing',
            'subject': 'Subject',
            'mailing_model_id': mailing_model.id,
            'mailing_domain': "[]",
            'body_html': '<p>Hello</p>',
            'use_in_marketing_automation': True,
        })
        campaign = self._create_campaign()
        activity = self._create_activity(
            campaign, activity_type='email', mass_mailing_id=mailing.id)
        self.assertEqual(activity.activity_type, 'email')
        self.assertEqual(activity.mass_mailing_id, mailing)
        # The mailing exposes its activities (the reverse one2many hook).
        self.assertIn(activity, mailing.marketing_activity_ids)
        # A mailing used by a campaign cannot be unlinked.
        from odoo.exceptions import UserError

        with self.assertRaises(UserError):
            mailing.unlink()
