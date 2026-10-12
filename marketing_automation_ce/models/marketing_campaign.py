# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from ast import literal_eval

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, modules, tools, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MarketingCampaign(models.Model):
    _name = 'marketing.campaign'
    _description = 'Marketing Campaign'
    _inherits = {'utm.campaign': 'utm_campaign_id'}
    _order = 'create_date DESC'

    utm_campaign_id = fields.Many2one(
        'utm.campaign', 'UTM Campaign', ondelete='restrict', required=True)
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'New'),
        ('running', 'Running'),
        ('stopped', 'Stopped'),
    ], copy=False, default='draft', group_expand=True)

    model_id = fields.Many2one(
        'ir.model', string='Model', index=True, required=True,
        ondelete='cascade',
        default=lambda self: self.env.ref(
            'base.model_res_partner', raise_if_not_found=False),
        domain="['&', ('is_mail_thread', '=', True), "
               "('model', '!=', 'mail.blacklist')]")
    model_name = fields.Char(
        string='Model Name', related='model_id.model', readonly=True,
        store=True)
    unique_field_id = fields.Many2one(
        'ir.model.fields', string='Unicity based on ',
        compute='_compute_unique_field_id', readonly=False, store=True,
        domain="[('model_id', '=', model_id), "
               "('ttype', 'in', ['char', 'integer', 'many2one', 'text', "
               "'selection'])]",
        help="Used to avoid duplicates based on a model field. For example, "
             "select the email field on Customers if you do not want to "
             "process records sharing the same email address.")
    domain = fields.Char(
        string='Filter', compute='_compute_domain', readonly=False,
        store=True)

    # ── Goal ────────────────────────────────────────────────────────────
    goal_domain = fields.Char(
        string='Goal',
        help="Domain evaluated against the participant's record. When a "
             "participant matches it, their flow ends and every scheduled "
             "activity is cancelled. Evaluated deterministically before each "
             "activity run.")

    # ── Re-enrollment policy ────────────────────────────────────────────
    reenrollment_policy = fields.Selection([
        ('never', 'Never'),
        ('once', 'Once'),
        ('after_delay', 'After a delay'),
    ], string='Re-enrollment', default='never', required=True,
        help="Whether a record that already went through this campaign may "
             "enter it again.")
    reenrollment_delay = fields.Integer(
        string='Re-enrollment delay', default=0)
    reenrollment_delay_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], string='Re-enrollment delay type', default='days', required=True)

    # ── Activities ──────────────────────────────────────────────────────
    marketing_activity_ids = fields.One2many(
        'marketing.activity', 'campaign_id', string='Activities',
        copy=False)
    mass_mailing_count = fields.Integer(
        '# Mailings', compute='_compute_mass_mailing_count')
    last_sync_date = fields.Datetime(
        string='Last activities synchronization', copy=False)
    require_sync = fields.Boolean(
        string='Sync of participants is required',
        compute='_compute_require_sync')

    # ── Participants ────────────────────────────────────────────────────
    participant_ids = fields.One2many(
        'marketing.participant', 'campaign_id', string='Participants',
        copy=False)
    running_participant_count = fields.Integer(
        string='# of active participants',
        compute='_compute_participants')
    completed_participant_count = fields.Integer(
        string='# of completed participants',
        compute='_compute_participants')
    total_participant_count = fields.Integer(
        string='# of active and completed participants',
        compute='_compute_participants')
    test_participant_count = fields.Integer(
        string='# of test participants', compute='_compute_participants')

    # ── Computes ────────────────────────────────────────────────────────

    @api.depends('model_id')
    def _compute_unique_field_id(self):
        for campaign in self:
            campaign.unique_field_id = False

    @api.depends('model_id')
    def _compute_domain(self):
        for campaign in self:
            campaign.domain = repr([])

    @api.depends('marketing_activity_ids.require_sync', 'last_sync_date',
                 'state')
    def _compute_require_sync(self):
        for campaign in self:
            if campaign.last_sync_date and campaign.state == 'running':
                changed = campaign.marketing_activity_ids.filtered(
                    lambda activity: activity.require_sync)
                campaign.require_sync = bool(changed)
            else:
                campaign.require_sync = False

    @api.depends('marketing_activity_ids.mass_mailing_id')
    def _compute_mass_mailing_count(self):
        for campaign in self:
            campaign.mass_mailing_count = len(
                campaign.mapped('marketing_activity_ids.mass_mailing_id'))

    @api.depends('participant_ids.state', 'participant_ids.is_test')
    def _compute_participants(self):
        participants_data = self.env['marketing.participant']._read_group(
            [('campaign_id', 'in', self.ids)],
            ['campaign_id', 'state', 'is_test'],
            ['__count'])
        mapped_data = {}
        for campaign, state, is_test, count in participants_data:
            data = mapped_data.setdefault(campaign.id, {})
            if is_test:
                data['is_test'] = data.get('is_test', 0) + count
            else:
                data[state] = data.get(state, 0) + count
        for campaign in self:
            data = mapped_data.get(campaign.id, {})
            campaign.running_participant_count = data.get('running', 0)
            campaign.completed_participant_count = data.get('completed', 0)
            campaign.total_participant_count = (
                campaign.completed_participant_count
                + campaign.running_participant_count)
            campaign.test_participant_count = data.get('is_test', 0)

    # ── Constraints ─────────────────────────────────────────────────────

    @api.constrains('reenrollment_policy', 'reenrollment_delay')
    def _check_reenrollment_delay(self):
        for campaign in self:
            if campaign.reenrollment_policy == 'after_delay' \
                    and campaign.reenrollment_delay <= 0:
                raise ValidationError(_(
                    "A re-enrollment delay must be greater than zero when "
                    "the policy is 'After a delay'."))

    @api.constrains('goal_domain')
    def _check_goal_domain(self):
        for campaign in self:
            if not campaign.goal_domain:
                continue
            try:
                domain = literal_eval(campaign.goal_domain)
            except (ValueError, SyntaxError):
                raise ValidationError(_(
                    "The goal domain is not a valid domain: %s",
                    campaign.goal_domain))
            if not isinstance(domain, list):
                raise ValidationError(_(
                    "The goal domain must be a list: %s",
                    campaign.goal_domain))

    # ── ORM ─────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({'is_auto_campaign': True})
        return super().create(vals_list)

    def write(self, vals):
        if not vals.get('active', True):
            vals['state'] = 'stopped'
        return super().write(vals)

    def copy(self, default=None):
        """Copy the campaign's activity tree, remapping parent relations.

        The copy inherits no traces, no participants and no sync date.
        """
        new_campaigns = super().copy(dict(default or {}))
        for old_campaign, new_campaign in zip(self, new_campaigns):
            old_to_new = {}
            for old_activity in old_campaign.marketing_activity_ids:
                new_activity = old_activity.copy()
                old_to_new[old_activity] = new_activity
                new_activity.write({
                    'campaign_id': new_campaign.id,
                    'require_sync': False,
                    'trace_ids': False,
                })
            for new_activity in new_campaign.marketing_activity_ids:
                new_activity.parent_id = old_to_new.get(new_activity.parent_id)
        return new_campaigns

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if any(c.marketing_activity_ids for c in self):
            return {'warning': {
                'title': _("Warning"),
                'message': _(
                    "Switching Target Model invalidates the existing "
                    "activities. Either update your activity actions to match "
                    "the new Target Model or delete them."),
            }}

    # ── Campaign lifecycle ──────────────────────────────────────────────

    def action_start_campaign(self):
        for campaign in self:
            if not campaign.marketing_activity_ids:
                raise ValidationError(_(
                    "You must set up at least one activity to start this "
                    "campaign."))
        self.write({'state': 'running'})
        self.sync_participants()
        return True

    def action_stop_campaign(self):
        self.write({'state': 'stopped'})
        return True

    def action_set_synchronized(self):
        """Reset the campaign's and its activities' sync flags."""
        self.write({'last_sync_date': fields.Datetime.now()})
        self.mapped('marketing_activity_ids').write({'require_sync': False})
        return True

    def action_view_mailings(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(
            'marketing_automation_ce.mail_mass_mailing_action_'
            'marketing_automation')
        action['domain'] = [
            ('id', 'in', self.mapped('marketing_activity_ids.mass_mailing_id').ids)]
        action['context'] = dict(self.env.context, create=False)
        return action

    # ── Participant synchronisation ─────────────────────────────────────

    def _get_record_domain(self):
        """Return the campaign's matching domain as a list."""
        self.ensure_one()
        return literal_eval(self.domain or '[]')

    def _reenrollment_allows(self, campaign, res_id, participant):
        """Decide whether a previously completed record may re-enter.

        :param participant: the existing participant for this record, if any.
        """
        if campaign.reenrollment_policy == 'never':
            return False
        if campaign.reenrollment_policy == 'once':
            # Allowed only if the record has never completed the flow.
            return participant.state != 'completed'
        # after_delay
        if not participant.completion_date:
            return True
        delay = relativedelta(**{
            campaign.reenrollment_delay_type: campaign.reenrollment_delay})
        return participant.completion_date + delay <= fields.Datetime.now()

    def sync_participants(self):
        """Synchronise participants against the campaign's domain.

        New matching records become participants, records that no longer
        match are marked removed, and re-enrollment is applied according to
        the campaign's policy.

        :return: the newly created participants
        """
        def _uniquify(seq):
            seen = set()
            return [x for x in seq if x not in seen and not seen.add(x)]

        new_participants = self.env['marketing.participant']
        now = fields.Datetime.now()
        # auto-commit except in testing mode
        auto_commit = not modules.module.current_test

        for campaign in self.filtered(lambda c: c.marketing_activity_ids):
            if not campaign.last_sync_date:
                campaign.last_sync_date = now

            user = campaign.user_id or self.env.user
            RecordModel = self.env[campaign.model_name].with_context(
                lang=user.lang)

            existing = self.env['marketing.participant'].search_read(
                [('campaign_id', '=', campaign.id)], ['res_id'])
            existing_ids = _uniquify([p['res_id'] for p in existing])

            record_domain = campaign._get_record_domain()
            db_ids = _uniquify(RecordModel.search(record_domain).ids)

            to_create = [rid for rid in db_ids if rid not in existing_ids]
            to_remove = set(existing_ids) - set(db_ids)

            # Uniqueness filtering on the chosen field.
            unique_field = campaign.unique_field_id.sudo()
            if unique_field and unique_field.name != 'id':
                without_duplicates = []
                existing_records = RecordModel.with_context(
                    prefetch_fields=False).browse(existing_ids).exists()
                unique_values = {
                    rec[unique_field.name]
                    for index in range(0, len(existing_records), 1000)
                    for rec in existing_records[index:index + 1000]
                }
                for rec in RecordModel.with_context(
                        prefetch_fields=False).browse(to_create):
                    field_val = rec[unique_field.name]
                    if (not unique_field.relation or field_val) \
                            and field_val not in unique_values:
                        without_duplicates.append(rec.id)
                        unique_values.add(field_val)
                to_create = without_duplicates

            # Re-enrollment: records that already have a completed
            # participant may re-enter only if the policy allows it.
            if campaign.reenrollment_policy != 'never' and to_create:
                completed = self.env['marketing.participant'].search([
                    ('campaign_id', '=', campaign.id),
                    ('res_id', 'in', to_create),
                    ('state', '=', 'completed'),
                ])
                blocked = set()
                for participant in completed:
                    if not campaign._reenrollment_allows(
                            campaign, participant.res_id, participant):
                        blocked.add(participant.res_id)
                if blocked:
                    to_create = [rid for rid in to_create
                                 if rid not in blocked]

            batch_size = 100
            for batch in tools.split_every(batch_size, to_create,
                                           piece_maker=list):
                new_participants += self.env['marketing.participant'].create([{
                    'campaign_id': campaign.id,
                    'res_id': rec_id,
                } for rec_id in batch])
                if auto_commit:
                    self.env.cr.commit()

            if to_remove:
                participants_to_unlink = self.env['marketing.participant'].search([
                    ('res_id', 'in', list(to_remove)),
                    ('campaign_id', '=', campaign.id),
                    ('state', '!=', 'unlinked'),
                ])
                for index in range(0, len(participants_to_unlink), 1000):
                    participants_to_unlink[index:index + 1000].action_set_unlink()
                    if auto_commit and not index % (batch_size * 100):
                        self.env.cr.commit()

        return new_participants

    # ── Flow execution ──────────────────────────────────────────────────

    def execute_activities(self):
        """Execute every scheduled activity whose deadline has passed."""
        for campaign in self:
            campaign.marketing_activity_ids.execute()
        return True

    def action_update_participants(self):
        """Apply activity changes to an already running campaign.

        Reschedules traces of modified activities and creates traces for
        activities added after the last synchronisation, without producing
        duplicates.
        """
        now = fields.Datetime.now()
        for campaign in self:
            modified = campaign.marketing_activity_ids.filtered(
                lambda a: a.require_sync)
            traces = self.env['marketing.trace'].search([
                ('state', '=', 'scheduled'),
                ('activity_id', 'in', modified.ids),
            ])
            traces._update_schedule_date()

            created = campaign.marketing_activity_ids.filtered(
                lambda a: campaign.last_sync_date
                and a.create_date >= campaign.last_sync_date)

            existing_traces = self.env['marketing.trace']
            if created:
                existing_traces = self.env['marketing.trace'].search([
                    ('activity_id', 'in', created.ids),
                ])

            for activity in created:
                offset = relativedelta(**{
                    activity.interval_type: activity.interval_number})
                with_traces = existing_traces.filtered(
                    lambda t: t.activity_id == activity).participant_id

                if activity.trigger_type == 'begin':
                    participants = self.env['marketing.participant'].search([
                        ('state', '=', 'running'),
                        ('campaign_id', '=', campaign.id),
                        ('id', 'not in', with_traces.ids),
                    ])
                    for participant in participants:
                        self.env['marketing.trace'].create({
                            'activity_id': activity.id,
                            'participant_id': participant.id,
                            'schedule_date': now + offset,
                        })
                else:
                    valid_parents = self.env['marketing.trace'].search([
                        ('state', '=', 'processed'),
                        ('activity_id', '=', activity.parent_id.id),
                        ('participant_id', 'not in', with_traces.ids),
                    ])
                    # Do not create a trace whose opposite branch already ran.
                    if activity.trigger_type in (
                            'mail_not_open', 'mail_not_click',
                            'mail_not_reply'):
                        opposite = activity.trigger_type.replace('_not_', '_')
                        brothers = self.env['marketing.trace'].search([
                            ('parent_id', 'in', valid_parents.ids),
                            ('trigger_type', '=', opposite),
                            ('state', '=', 'processed'),
                        ])
                        valid_parents = valid_parents - brothers.mapped(
                            'parent_id')

                    valid_parents.mapped('participant_id').filtered(
                        lambda p: p.state == 'completed'
                    ).action_set_running()

                    for parent_trace in valid_parents:
                        self.env['marketing.trace'].create({
                            'activity_id': activity.id,
                            'participant_id': parent_trace.participant_id.id,
                            'parent_id': parent_trace.id,
                            'schedule_date': fields.Datetime.from_string(
                                parent_trace.schedule_date) + offset,
                        })

        self.action_set_synchronized()
        return True
