# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from ast import literal_eval
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, modules, _
from odoo.exceptions import AccessError, ValidationError
from odoo.osv import expression
from odoo.tools.misc import clean_context

_logger = logging.getLogger(__name__)

# Trigger types that are scheduled by time rather than by an external event.
RESCHEDULE_TRIGGER_TYPES = {
    'begin', 'activity', 'mail_not_open', 'mail_not_click', 'mail_not_reply',
}

# Trigger types driven by a mail reaction.
MAIL_TRIGGER_TYPES = {
    'mail_open', 'mail_not_open', 'mail_reply', 'mail_not_reply',
    'mail_click', 'mail_not_click', 'mail_bounce',
}


class MarketingActivity(models.Model):
    _name = 'marketing.activity'
    _description = 'Marketing Activity'
    _inherit = ['utm.source.mixin']
    _order = 'interval_standardized, id ASC'

    name = fields.Char(string='Activity Name', required=True)
    activity_type = fields.Selection([
        ('email', 'Email'),
        ('action', 'Server Action'),
        ('condition', 'Condition'),
    ], string='Activity Type', required=True, default='email')
    campaign_id = fields.Many2one(
        'marketing.campaign', string='Campaign', index=True,
        ondelete='cascade', required=True)
    utm_campaign_id = fields.Many2one(
        'utm.campaign', string='UTM Campaign', readonly=True,
        related='campaign_id.utm_campaign_id')
    model_id = fields.Many2one(
        'ir.model', related='campaign_id.model_id', string='Model',
        readonly=True)
    model_name = fields.Char(
        related='model_id.model', string='Model Name', readonly=True)

    # ── Target ──────────────────────────────────────────────────────────
    mass_mailing_id = fields.Many2one(
        'mailing.mailing', string='Marketing Template',
        compute='_compute_mass_mailing_id', readonly=False, store=True,
        index='btree_not_null')
    server_action_id = fields.Many2one(
        'ir.actions.server', string='Server Action',
        compute='_compute_server_action_id', readonly=False, store=True)

    # ── Interval ────────────────────────────────────────────────────────
    interval_number = fields.Integer(string='Send after', default=0)
    interval_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], string='Delay Type', default='hours', required=True)
    interval_standardized = fields.Integer(
        'Send after (in hours)', compute='_compute_interval_standardized',
        store=True, readonly=True)

    # ── Validity ────────────────────────────────────────────────────────
    validity_duration = fields.Boolean(
        'Validity Duration',
        help="Check this to make sure your actions are not executed after a "
             "specific amount of time after the scheduled date. For example "
             "a time-limited offer or an upcoming event.")
    validity_duration_number = fields.Integer(string='Valid during', default=0)
    validity_duration_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], default='hours', required=True)

    # ── Condition step ──────────────────────────────────────────────────
    condition_domain = fields.Char(
        string='Condition',
        help="Domain evaluated against the participant's record. The 'true' "
             "branch runs when the record matches it, the 'false' branch "
             "otherwise.")
    condition_wait = fields.Boolean(
        string='Wait until the condition holds',
        help="When set, the step is re-evaluated at each run instead of "
             "deciding immediately, until the timeout is reached.")
    condition_timeout = fields.Integer(string='Timeout', default=0)
    condition_timeout_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], string='Timeout type', default='days', required=True)

    # ── Domain ──────────────────────────────────────────────────────────
    activity_domain = fields.Char(
        string='Activity Filter', default='[]',
        help="Domain that applies to this activity and its child activities.")
    domain = fields.Char(
        string='Applied Filter',
        help="Activity will only be performed if the record satisfies this "
             "domain, obtained from the combination of the activity filter "
             "and its inherited filters.",
        compute='_compute_inherited_domain', recursive=True, store=True,
        readonly=True)

    # ── Tree ────────────────────────────────────────────────────────────
    parent_id = fields.Many2one(
        'marketing.activity', string='Activity',
        compute='_compute_parent_id', index=True, readonly=False,
        store=True, ondelete='cascade')
    allowed_parent_ids = fields.Many2many(
        'marketing.activity', string='Allowed parents',
        help='All activities which can be the parent of this one',
        compute='_compute_allowed_parent_ids')
    child_ids = fields.One2many(
        'marketing.activity', 'parent_id', string='Child Activities')
    true_child_ids = fields.One2many(
        'marketing.activity', 'condition_true_parent_id',
        string='True branch')
    false_child_ids = fields.One2many(
        'marketing.activity', 'condition_false_parent_id',
        string='False branch')
    condition_true_parent_id = fields.Many2one(
        'marketing.activity', string='Condition (true)',
        ondelete='cascade', copy=False)
    condition_false_parent_id = fields.Many2one(
        'marketing.activity', string='Condition (false)',
        ondelete='cascade', copy=False)

    trigger_type = fields.Selection([
        ('begin', 'beginning of workflow'),
        ('activity', 'another activity'),
        ('mail_open', 'Mail: opened'),
        ('mail_not_open', 'Mail: not opened'),
        ('mail_reply', 'Mail: replied'),
        ('mail_not_reply', 'Mail: not replied'),
        ('mail_click', 'Mail: clicked'),
        ('mail_not_click', 'Mail: not clicked'),
        ('mail_bounce', 'Mail: bounced'),
    ], default='begin', required=True)
    trigger_category = fields.Selection(
        [('email', 'Mail')], compute='_compute_trigger_category')

    # ── Cron / sync ─────────────────────────────────────────────────────
    require_sync = fields.Boolean('Require trace sync', copy=False)

    # ── Traces ──────────────────────────────────────────────────────────
    trace_ids = fields.One2many(
        'marketing.trace', 'activity_id', string='Traces', copy=False)
    processed = fields.Integer(compute='_compute_statistics')
    rejected = fields.Integer(compute='_compute_statistics')
    total_sent = fields.Integer(compute='_compute_statistics')
    total_click = fields.Integer(compute='_compute_statistics')
    total_open = fields.Integer(compute='_compute_statistics')
    total_reply = fields.Integer(compute='_compute_statistics')
    total_bounce = fields.Integer(compute='_compute_statistics')
    statistics_graph_data = fields.Char(
        compute='_compute_statistics_graph_data')

    # ── Computes ────────────────────────────────────────────────────────

    @api.depends('activity_type')
    def _compute_mass_mailing_id(self):
        for activity in self:
            if activity.activity_type != 'email':
                activity.mass_mailing_id = False

    @api.depends('activity_type')
    def _compute_server_action_id(self):
        for activity in self:
            if activity.activity_type != 'action':
                activity.server_action_id = False

    @api.depends('interval_type', 'interval_number')
    def _compute_interval_standardized(self):
        factors = {'hours': 1, 'days': 24, 'weeks': 168, 'months': 720}
        for activity in self:
            activity.interval_standardized = (
                activity.interval_number * factors[activity.interval_type])

    @api.depends('activity_domain', 'campaign_id.domain', 'parent_id.domain')
    def _compute_inherited_domain(self):
        for activity in self:
            domains = [
                literal_eval(activity.activity_domain or '[]'),
                literal_eval(activity.campaign_id.domain or '[]'),
            ]
            ancestor = activity.parent_id
            while ancestor:
                domains.append(
                    literal_eval(ancestor.activity_domain or '[]'))
                ancestor = ancestor.parent_id
            activity.domain = expression.AND(domains)

    @api.depends('trigger_type')
    def _compute_parent_id(self):
        for activity in self:
            if not activity.parent_id or activity.trigger_type == 'begin':
                activity.parent_id = False

    @api.depends('trigger_type', 'campaign_id.marketing_activity_ids',
                 'activity_type')
    def _compute_allowed_parent_ids(self):
        for activity in self:
            siblings = activity.campaign_id.marketing_activity_ids.filtered(
                lambda a: a.ids != activity.ids)
            if activity.trigger_type == 'activity':
                activity.allowed_parent_ids = siblings
            elif activity.trigger_category:
                activity.allowed_parent_ids = siblings.filtered(
                    lambda a: a.activity_type == activity.trigger_category)
            else:
                activity.allowed_parent_ids = False

    @api.depends('trigger_type')
    def _compute_trigger_category(self):
        for activity in self:
            activity.trigger_category = (
                'email' if activity.trigger_type in MAIL_TRIGGER_TYPES
                else False)

    @api.depends('activity_type', 'trace_ids')
    def _compute_statistics(self):
        self.update({
            'total_bounce': 0, 'total_reply': 0, 'total_sent': 0,
            'rejected': 0, 'total_click': 0, 'processed': 0, 'total_open': 0,
        })
        if self.ids:
            activity_data = {activity._origin.id: {} for activity in self}
            for stat in self._get_full_statistics():
                activity_data[stat.pop('activity_id')].update(stat)
            for activity in self:
                activity.update(activity_data[activity._origin.id])

    @api.depends('activity_type', 'trace_ids')
    def _compute_statistics_graph_data(self):
        if not self.ids:
            date_range = [date.today() - timedelta(days=d) for d in range(15)]
            date_range.reverse()
            default = [{'x': d.strftime('%d %b'), 'y': 0} for d in date_range]
            self.statistics_graph_data = json.dumps([
                {'points': default, 'label': _('Success'), 'color': '#28A745'},
                {'points': default, 'label': _('Rejected'), 'color': '#D23f3A'},
            ])
        else:
            activity_data = {activity._origin.id: {} for activity in self}
            for act_id, graph_data in self._get_graph_statistics().items():
                activity_data[act_id]['statistics_graph_data'] = json.dumps(
                    graph_data)
            for activity in self:
                activity.update(activity_data[activity._origin.id])

    # ── Constraints ─────────────────────────────────────────────────────

    @api.constrains('trigger_type', 'parent_id')
    def _check_consistency_in_activities(self):
        for activity in self:
            if (activity.parent_id or activity.allowed_parent_ids) \
                    and activity.parent_id not in activity.allowed_parent_ids:
                trigger = dict(
                    activity._fields['trigger_type']
                    ._description_selection(self.env)
                )[activity.trigger_type]
                raise ValidationError(_(
                    'You are trying to set the activity "%(parent)s" as '
                    '"%(ptype)s" while its child "%(child)s" has the trigger '
                    'type "%(trigger)s".\nPlease modify one of those '
                    'activities before saving.',
                    parent=activity.parent_id.name,
                    ptype=activity.parent_id.activity_type,
                    child=activity.name,
                    trigger=trigger))

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle():
            raise ValidationError(_(
                "Error! You can't create recursive hierarchy of Activity."))

    @api.constrains('activity_type', 'condition_wait', 'condition_timeout')
    def _check_condition_step(self):
        for activity in self:
            if activity.activity_type != 'condition':
                continue
            if activity.condition_wait and activity.condition_timeout <= 0:
                raise ValidationError(_(
                    "A condition step that waits for its condition must have "
                    "a timeout greater than zero: %s", activity.name))

    @api.constrains('activity_type', 'mass_mailing_id', 'server_action_id')
    def _check_activity_payload(self):
        for activity in self:
            if activity.activity_type == 'email' \
                    and not activity.mass_mailing_id:
                raise ValidationError(_(
                    "An email activity requires a mail template: %s",
                    activity.name))
            if activity.activity_type == 'action' \
                    and not activity.server_action_id:
                raise ValidationError(_(
                    "A server action activity requires a server action: %s",
                    activity.name))

    # ── ORM ─────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            campaign_id = values.get('campaign_id')
            if not campaign_id:
                campaign_id = self.default_get(['campaign_id'])['campaign_id']
            values['require_sync'] = (
                self.env['marketing.campaign'].browse(campaign_id).state
                == 'running')
        return super().create(vals_list)

    def copy_data(self, default=None):
        default = dict(default or {})
        if self.mass_mailing_id:
            default['mass_mailing_id'] = self.mass_mailing_id.copy().id
        return super().copy_data(default=default)

    def write(self, vals):
        if any(a.campaign_id.state == 'running' for a in self) \
                and any(f in vals for f in ('interval_number', 'interval_type')):
            vals['require_sync'] = True
        return super().write(vals)

    # ── Statistics ──────────────────────────────────────────────────────

    def _get_full_statistics(self):
        self.env['marketing.trace'].flush_model(
            ['activity_id', 'participant_id', 'state'])
        self.env['mailing.trace'].flush_model(
            ['marketing_trace_id', 'links_click_datetime', 'sent_datetime',
             'trace_status'])
        self.env['marketing.participant'].flush_model(['is_test'])
        self.env.cr.execute("""
            SELECT
                trace.activity_id,
                COUNT(stat.sent_datetime) AS total_sent,
                COUNT(stat.links_click_datetime) AS total_click,
                COUNT(stat.trace_status) FILTER (
                    WHERE stat.trace_status = 'reply') AS total_reply,
                COUNT(stat.trace_status) FILTER (
                    WHERE stat.trace_status IN ('open', 'reply')) AS total_open,
                COUNT(stat.trace_status) FILTER (
                    WHERE stat.trace_status = 'bounce') AS total_bounce,
                COUNT(trace.state) FILTER (
                    WHERE trace.state = 'processed') AS processed,
                COUNT(trace.state) FILTER (
                    WHERE trace.state = 'rejected') AS rejected
            FROM marketing_trace AS trace
            LEFT JOIN mailing_trace AS stat
                ON (stat.marketing_trace_id = trace.id)
            JOIN marketing_participant AS part
                ON (trace.participant_id = part.id)
            WHERE (part.is_test = false OR part.is_test IS NULL)
              AND trace.activity_id IN %s
            GROUP BY trace.activity_id;
        """, (tuple(self.ids),))
        return self.env.cr.dictfetchall()

    def _get_graph_statistics(self):
        """Statistics per activity over the last fortnight."""
        past_date = (fields.Datetime.now() + timedelta(days=-14)).strftime(
            '%Y-%m-%d 00:00:00')
        stat_map = {}
        base = date.today() + timedelta(days=-14)
        date_range = [base + timedelta(days=d) for d in range(15)]

        self.env['marketing.trace'].flush_model(
            ['activity_id', 'is_test', 'schedule_date', 'state'])
        self.env.cr.execute("""
            SELECT
                activity.id AS activity_id,
                trace.schedule_date::date AS dt,
                count(*) AS total,
                trace.state
            FROM marketing_trace AS trace
            JOIN marketing_activity AS activity
                ON (activity.id = trace.activity_id)
            WHERE activity.id IN %s
              AND trace.schedule_date >= %s
              AND (trace.is_test = false OR trace.is_test IS NULL)
            GROUP BY activity.id, dt, trace.state
            ORDER BY dt;
        """, (tuple(self.ids), past_date))

        for stat in self.env.cr.dictfetchall():
            stat_map[(stat['activity_id'], stat['dt'], stat['state'])] = \
                stat['total']

        graph_data = {}
        for activity in self:
            success, rejected = [], []
            for day in date_range:
                x = day.strftime('%d %b')
                success.append({
                    'x': x,
                    'y': stat_map.get(
                        (activity._origin.id, day, 'processed'), 0),
                })
                rejected.append({
                    'x': x,
                    'y': stat_map.get(
                        (activity._origin.id, day, 'rejected'), 0),
                })
            graph_data[activity._origin.id] = [
                {'points': success, 'label': _('Success'), 'color': '#28A745'},
                {'points': rejected, 'label': _('Rejected'),
                 'color': '#D23f3A'},
            ]
        return graph_data

    # ── Execution ───────────────────────────────────────────────────────

    def execute(self, domain=None):
        """Execute every scheduled trace whose deadline has passed."""
        auto_commit = not modules.module.current_test
        trace_domain = [
            ('schedule_date', '<=', fields.Datetime.now()),
            ('state', '=', 'scheduled'),
            ('activity_id', 'in', self.ids),
            ('participant_id.state', '=', 'running'),
        ]
        if domain:
            trace_domain += domain

        trace_to_activities = {
            activity: traces
            for activity, traces in self.env['marketing.trace']._read_group(
                trace_domain, groupby=['activity_id'],
                aggregates=['id:recordset'])
        }

        batch_size = 500
        for activity, traces in trace_to_activities.items():
            for batch in (traces[i:i + batch_size]
                          for i in range(0, len(traces), batch_size)):
                activity.execute_on_traces(batch)
                if auto_commit:
                    self.env.cr.commit()

    def execute_on_traces(self, traces):
        """Execute this activity on the given traces."""
        self.ensure_one()
        now = fields.Datetime.now()
        new_traces = self.env['marketing.trace']

        # Validity window: cancel traces that are past their validity.
        if self.validity_duration:
            duration = relativedelta(**{
                self.validity_duration_type: self.validity_duration_number})
            invalid = traces.filtered(
                lambda t: not t.schedule_date
                or t.schedule_date + duration < now)
            invalid.action_cancel(message=_('Expired'))
            traces = traces - invalid

        # Filter on the applied domain and on deleted/archived records.
        rec_domain = literal_eval(self.domain) if self.domain \
            else literal_eval(self.campaign_id.domain or '[]')
        if rec_domain:
            user = self.campaign_id.user_id or self.env.user
            valid_ids = self.env[self.model_name].with_context(
                lang=user.lang).search(rec_domain).ids
            traces_allowed = traces.filtered(lambda t: t.res_id in valid_ids)
            traces_rejected = traces - traces_allowed
        else:
            traces_allowed = traces
            traces_rejected = self.env['marketing.trace']

        if traces_allowed:
            activity_method = getattr(self, '_execute_%s' % self.activity_type)
            new_traces += self._generate_children_traces(traces_allowed)
            activity_method(traces_allowed)
            traces.mapped('participant_id').check_completed()

        if traces_rejected:
            traces_rejected.write({
                'state': 'rejected',
                'state_msg': _(
                    'Rejected by activity filter or record deleted / archived'),
            })
            traces_rejected.mapped('participant_id').check_completed()

        return new_traces

    def _execute_email(self, traces):
        if not self.env.is_superuser() \
                and not self.env.user.has_group(
                    'marketing_automation_ce.group_marketing_automation_user'):
            raise AccessError(_(
                "To use this feature you should be an administrator or "
                "belong to the marketing automation group."))

        def _uniquify(seq):
            seen = set()
            return [x for x in seq if x not in seen and not seen.add(x)]

        res_ids = _uniquify(traces.mapped('res_id'))
        ctx = dict(clean_context(self.env.context),
                   default_marketing_activity_id=self.ids[0],
                   active_ids=res_ids)
        mailing = self.mass_mailing_id.sudo().with_context(ctx)
        now = fields.Datetime.now()

        try:
            mailing.action_send_mail(res_ids)
        except Exception as error:
            _logger.warning(
                'Marketing Automation: activity <%s> encountered mass mailing '
                'issue %s', self.id, error, exc_info=True)
            traces.write({
                'state': 'error',
                'schedule_date': now,
                'state_msg': _('Exception in mass mailing: %s', error),
            })
            return True

        failed = self.env['mailing.trace'].sudo().search([
            ('marketing_trace_id', 'in', traces.ids),
            ('trace_status', 'in', ['error', 'bounce', 'cancel']),
        ])
        error_ids = [s.res_id for s in failed
                     if s.trace_status in ('error', 'bounce')]
        cancel_ids = [s.res_id for s in failed if s.trace_status == 'cancel']

        processed = traces
        canceled = traces.filtered(lambda t: t.res_id in cancel_ids)
        errored = traces.filtered(lambda t: t.res_id in error_ids)

        if canceled:
            canceled.write({
                'state': 'canceled',
                'schedule_date': now,
                'state_msg': _('Email cancelled'),
            })
            processed -= canceled
        if errored:
            errored.write({
                'state': 'error',
                'schedule_date': now,
                'state_msg': _('Email failed'),
            })
            processed -= errored
        if processed:
            processed.write({'state': 'processed', 'schedule_date': now})
        return True

    def _execute_action(self, traces):
        if not self.server_action_id:
            return False
        now = fields.Datetime.now()
        traces_ok = self.env['marketing.trace']
        for trace in traces:
            action = self.server_action_id.with_context(
                active_model=self.model_name,
                active_ids=[trace.res_id],
                active_id=trace.res_id)
            try:
                action.run()
            except Exception as error:
                _logger.warning(
                    'Marketing Automation: activity <%s> encountered server '
                    'action issue %s', self.id, error, exc_info=True)
                trace.write({
                    'state': 'error',
                    'schedule_date': now,
                    'state_msg': _('Exception in server action: %s', error),
                })
            else:
                traces_ok += trace
        traces_ok.write({'state': 'processed', 'schedule_date': now})
        return True

    def _execute_condition(self, traces):
        """Evaluate the condition and route traces to the matching branch.

        With ``condition_wait`` the step is re-evaluated at each run until the
        condition holds or the timeout is reached.
        """
        self.ensure_one()
        now = fields.Datetime.now()
        rec_domain = literal_eval(self.condition_domain or '[]')

        for trace in traces:
            record = self.env[self.model_name].browse(trace.res_id).exists()
            matched = bool(record) and bool(
                self.env[self.model_name].search(
                    rec_domain + [('id', '=', trace.res_id)], limit=1))

            if not matched and self.condition_wait:
                deadline = fields.Datetime.from_string(
                    trace.schedule_date) + relativedelta(**{
                        self.condition_timeout_type: self.condition_timeout})
                if deadline > now:
                    # Keep waiting: re-schedule for the next run.
                    trace.write({'schedule_date': now})
                    continue

            # Decide: route to the true or the false branch.
            branch = self.true_child_ids if matched \
                else self.false_child_ids
            other = self.false_child_ids if matched else self.true_child_ids
            trace.write({
                'state': 'processed',
                'schedule_date': now,
                'state_msg': _('Condition matched') if matched
                else _('Condition not matched'),
            })
            self._generate_branch_traces(trace, branch)
            # The branch not taken is cancelled for this participant.
            self._cancel_branch_traces(trace, other)

        traces.mapped('participant_id').check_completed()
        return True

    def _generate_branch_traces(self, trace, branch_activities):
        """Create child traces for the chosen condition branch."""
        new_traces = self.env['marketing.trace']
        for activity in branch_activities:
            offset = relativedelta(**{
                activity.interval_type: activity.interval_number})
            vals = {
                'parent_id': trace.id,
                'participant_id': trace.participant_id.id,
                'activity_id': activity.id,
            }
            if activity.trigger_type in RESCHEDULE_TRIGGER_TYPES:
                vals['schedule_date'] = \
                    fields.Datetime.from_string(trace.schedule_date) + offset
            new_traces += new_traces.create(vals)
        return new_traces

    def _cancel_branch_traces(self, trace, branch_activities):
        """Cancel scheduled traces of the branch that was not taken."""
        if not branch_activities:
            return
        traces = self.env['marketing.trace'].search([
            ('parent_id', '=', trace.id),
            ('activity_id', 'in', branch_activities.ids),
            ('state', '=', 'scheduled'),
        ])
        if traces:
            traces.action_cancel(message=_('Other condition branch taken'))

    def _generate_children_traces(self, traces):
        """Create child traces for the time-dependent child activities."""
        child_traces = self.env['marketing.trace']
        for activity in self.child_ids:
            offset = relativedelta(**{
                activity.interval_type: activity.interval_number})
            for trace in traces:
                vals = {
                    'parent_id': trace.id,
                    'participant_id': trace.participant_id.id,
                    'activity_id': activity.id,
                }
                if activity.trigger_type in RESCHEDULE_TRIGGER_TYPES:
                    vals['schedule_date'] = \
                        fields.Datetime.from_string(trace.schedule_date) \
                        + offset
                child_traces += child_traces.create(vals)
        return child_traces

    def _get_reschedule_trigger_types(self):
        return RESCHEDULE_TRIGGER_TYPES

    # ── Actions ─────────────────────────────────────────────────────────

    def action_view_sent(self):
        return self._action_view_documents_filtered('sent')

    def action_view_replied(self):
        return self._action_view_documents_filtered('reply')

    def action_view_clicked(self):
        return self._action_view_documents_filtered('click')

    def action_view_opened(self):
        return self._action_view_documents_filtered('open')

    def _action_view_documents_filtered(self, view_filter):
        if not self.mass_mailing_id:
            return False
        action = self.env['ir.actions.actions']._for_xml_id(
            'marketing_automation_ce.marketing_participants_action_mail')
        if view_filter == 'reply':
            found = self.trace_ids.filtered(
                lambda t: t.mailing_trace_status == view_filter)
        elif view_filter == 'open':
            found = self.trace_ids.filtered(
                lambda t: t.mailing_trace_status in ('open', 'reply'))
        elif view_filter == 'sent':
            found = self.trace_ids.filtered('mailing_trace_ids.sent_datetime')
        elif view_filter == 'click':
            found = self.trace_ids.filtered(
                'mailing_trace_ids.links_click_datetime')
        else:
            found = self.env['marketing.trace']
        participants = found.participant_id
        action.update({
            'display_name': _(
                'Participants of %(activity)s (%(filter)s)',
                activity=self.name, filter=view_filter),
            'domain': [('id', 'in', participants.ids)],
            'context': dict(self.env.context, create=False),
        })
        return action
