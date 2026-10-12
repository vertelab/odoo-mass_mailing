# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from ast import literal_eval

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

# Triggers whose schedule date depends on the parent or the campaign, not on
# an external user action.
RESCHEDULE_TRIGGER_TYPES = {
    'begin', 'activity', 'mail_not_open', 'mail_not_click', 'mail_not_reply',
}


class MarketingTrace(models.Model):
    _name = 'marketing.trace'
    _description = 'Marketing Trace'
    _order = 'schedule_date DESC, id ASC'
    _rec_name = 'participant_id'

    participant_id = fields.Many2one(
        'marketing.participant', string='Participant', index=True,
        ondelete='cascade', required=True)
    res_id = fields.Integer(
        string='Document ID', related='participant_id.res_id', index=True,
        store=True, readonly=False)
    is_test = fields.Boolean(
        string='Test Trace', related='participant_id.is_test', index=True,
        store=True, readonly=True)
    activity_id = fields.Many2one(
        'marketing.activity', string='Activity', index=True,
        ondelete='cascade', required=True)
    activity_type = fields.Selection(
        related='activity_id.activity_type', readonly=True)
    trigger_type = fields.Selection(
        related='activity_id.trigger_type', readonly=True)
    model_name = fields.Char(
        related='participant_id.model_name', readonly=True)

    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('processed', 'Processed'),
        ('rejected', 'Rejected'),
        ('canceled', 'Cancelled'),
        ('error', 'Error'),
    ], default='scheduled', index=True, required=True)
    schedule_date = fields.Datetime()
    state_msg = fields.Char(string='Error message')

    # ── Goal ────────────────────────────────────────────────────────────
    goal_met = fields.Boolean(
        string='Goal met', compute='_compute_goal_met', store=True,
        index=True,
        help="Whether the campaign's goal domain matches this participant's "
             "record. Stored so that automation rules can filter on it.")

    # ── Hierarchy ───────────────────────────────────────────────────────
    parent_id = fields.Many2one(
        'marketing.trace', string='Parent', index=True, ondelete='cascade')
    child_ids = fields.One2many(
        'marketing.trace', 'parent_id', string='Direct child traces')

    # ── Mailing traces ──────────────────────────────────────────────────
    mailing_trace_ids = fields.One2many(
        'mailing.trace', 'marketing_trace_id',
        string='Mass mailing statistics')
    mailing_trace_status = fields.Selection(
        related='mailing_trace_ids.trace_status', readonly=True)
    links_click_datetime = fields.Datetime(
        compute='_compute_links_click_datetime')

    @api.depends('participant_id', 'participant_id.campaign_id.goal_domain',
                 'res_id')
    def _compute_goal_met(self):
        for trace in self:
            campaign = trace.participant_id.campaign_id
            if not campaign.goal_domain or not trace.res_id \
                    or not trace.model_name:
                trace.goal_met = False
                continue
            try:
                domain = literal_eval(campaign.goal_domain)
            except (ValueError, SyntaxError):
                trace.goal_met = False
                continue
            if not trace.model_name in self.env:
                trace.goal_met = False
                continue
            trace.goal_met = bool(self.env[trace.model_name].search(
                domain + [('id', '=', trace.res_id)], limit=1))

    @api.depends('mailing_trace_ids')
    def _compute_links_click_datetime(self):
        self.links_click_datetime = False
        for trace in self.filtered(lambda t: t.mailing_trace_ids):
            trace.links_click_datetime = \
                trace.mailing_trace_ids[0].links_click_datetime

    # ── Actions ─────────────────────────────────────────────────────────

    def participant_action_cancel(self):
        self.action_cancel(message=_('Manually'))

    def action_cancel(self, message=None):
        values = {'state': 'canceled', 'schedule_date': fields.Datetime.now()}
        if message:
            values['state_msg'] = message
        self.write(values)
        self.mapped('participant_id').check_completed()

    def action_execute(self):
        self.activity_id.execute_on_traces(self)

    def process_event(self, action):
        """Process a mail reaction and update the child traces.

        The child trace matching the action is scheduled or executed
        depending on its interval; opposite branches are cancelled.

        :param str action: one of the mail trigger types
        """
        self.ensure_one()
        if self.participant_id.campaign_id.state not in ('draft', 'running'):
            return False

        now = fields.Datetime.now()
        messages = {
            'mail_not_reply': _('Parent activity mail replied'),
            'mail_not_click': _('Parent activity mail clicked'),
            'mail_not_open': _('Parent activity mail opened'),
            'mail_bounce': _('Parent activity mail bounced'),
        }

        opened_child = self.child_ids.filtered(
            lambda t: t.state == 'scheduled')

        for next_trace in opened_child.filtered(
                lambda t: t.activity_id.trigger_type == action):
            if next_trace.activity_id.interval_number == 0:
                next_trace.write({'schedule_date': now})
                next_trace.activity_id.execute_on_traces(next_trace)
            else:
                schedule_date = now + relativedelta(**{
                    next_trace.activity_id.interval_type:
                        next_trace.activity_id.interval_number})
                next_trace.write({'schedule_date': schedule_date})

        if action in ('mail_reply', 'mail_click', 'mail_open'):
            opposite = action.replace('_', '_not_')
            opened_child.filtered(
                lambda t: t.activity_id.trigger_type == opposite
            ).action_cancel(message=messages[opposite])
        elif action == 'mail_bounce':
            opened_child.filtered(
                lambda t: t.activity_id.trigger_type != 'mail_bounce'
            ).action_cancel(message=messages[action])

        return True

    def _update_schedule_date(self):
        """Recompute schedule dates after an activity interval change."""
        reschedule_types = RESCHEDULE_TRIGGER_TYPES
        for trace in self:
            base_dt_str = False
            offset = relativedelta(**{
                trace.activity_id.interval_type:
                    trace.activity_id.interval_number})
            if trace.activity_id.trigger_type == 'begin':
                base_dt_str = trace.participant_id.create_date
            elif trace.trigger_type in reschedule_types:
                base_dt_str = (
                    trace.parent_id.schedule_date
                    or (trace.parent_id.mailing_trace_ids
                        and trace.parent_id.mailing_trace_ids[0].write_date)
                    or trace.participant_id.create_date)
            elif trace.schedule_date and trace.parent_id.mailing_trace_ids:
                base_dt_str = trace.parent_id.mailing_trace_ids[0].write_date

            if base_dt_str:
                trace.schedule_date = \
                    fields.Datetime.from_string(base_dt_str) + offset
