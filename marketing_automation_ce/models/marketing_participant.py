# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.osv import expression


class MarketingParticipant(models.Model):
    _name = 'marketing.participant'
    _description = 'Marketing Participant'
    _order = 'id ASC'
    _rec_name = 'resource_ref'

    campaign_id = fields.Many2one(
        'marketing.campaign', string='Campaign', index=True,
        ondelete='cascade', required=True)
    model_id = fields.Many2one(
        'ir.model', string='Model', related='campaign_id.model_id',
        index=True, readonly=True, store=True)
    model_name = fields.Char(
        string='Record model', related='campaign_id.model_id.model',
        readonly=True, store=True)
    res_id = fields.Integer(string='Record ID', index=True)
    resource_ref = fields.Reference(
        string='Record', selection='_selection_target_model',
        compute='_compute_resource_ref', inverse='_set_resource_ref',
        search='_search_resource_ref')
    trace_ids = fields.One2many(
        'marketing.trace', 'participant_id', string='Actions')
    state = fields.Selection([
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('unlinked', 'Removed'),
    ], default='running', index=True, required=True,
        help='Removed means the related record does not exist anymore.')
    is_test = fields.Boolean('Test Record', default=False)
    completion_date = fields.Datetime(
        string='Completed on', readonly=True, copy=False,
        help="When the participant completed the flow. Used by the "
             "re-enrollment policy.")

    @api.model
    def _selection_target_model(self):
        models = self.env['ir.model'].sudo().search(
            [('is_mail_thread', '=', True)])
        return [(model.model, model.name) for model in models]

    def _search_resource_ref(self, operator, value):
        if operator in expression.NEGATIVE_TERM_OPERATORS:
            return NotImplemented
        ir_model_ids = []
        for [model_name] in self.env['marketing.campaign']._read_group(
                [], ['model_name']):
            model = self.env.get(model_name)
            if model is None:
                continue
            ir_model_ids += self.search(
                ['&', ('model_name', '=', model_name),
                 ('res_id', 'in',
                  [name[0] for name in model.name_search(name=value)])],
                order='id').ids
        return [('id', 'in', ir_model_ids)]

    @api.depends('model_name', 'res_id')
    def _compute_resource_ref(self):
        for participant in self:
            if participant.model_name and participant.model_name in self.env:
                participant.resource_ref = '%s,%s' % (
                    participant.model_name, participant.res_id or 0)
            else:
                participant.resource_ref = None

    def _set_resource_ref(self):
        for participant in self:
            if participant.resource_ref:
                participant.res_id = participant.resource_ref.id

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if 'res_id' in fields_list and not defaults.get('res_id'):
            model_name = defaults.get('model_name')
            if not model_name and defaults.get('campaign_id'):
                model_name = self.env['marketing.campaign'].browse(
                    defaults['campaign_id']).model_name
            if model_name and model_name in self.env:
                resource = self.env[model_name].search([], limit=1)
                defaults['res_id'] = resource.id
        return defaults

    # ── Lifecycle ───────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        participants = super().create(vals_list)
        now = fields.Datetime.now()
        for participant in participants:
            primary = participant.campaign_id.marketing_activity_ids.filtered(
                lambda a: a.trigger_type == 'begin')
            participant.write({'trace_ids': [
                (0, 0, {
                    'activity_id': activity.id,
                    'schedule_date': now + relativedelta(**{
                        activity.interval_type: activity.interval_number}),
                }) for activity in primary
            ]})
        return participants

    def check_completed(self):
        """Mark participants with no remaining scheduled trace as completed."""
        still_scheduled = self.env['marketing.trace'].search([
            ('participant_id', 'in', self.ids),
            ('state', '=', 'scheduled'),
        ])
        to_complete = self - still_scheduled.mapped('participant_id')
        if to_complete:
            to_complete.write({
                'state': 'completed',
                'completion_date': fields.Datetime.now(),
            })

    def action_set_completed(self):
        """Manually mark as completed and cancel every scheduled trace."""
        self._action_set_completed(trace_message=_('Marked as completed'))

    def _action_set_completed(self, trace_message=False):
        self.write({
            'state': 'completed',
            'completion_date': fields.Datetime.now(),
        })
        trace_vals = {
            'state': 'canceled',
            'schedule_date': fields.Datetime.now(),
        }
        if trace_message:
            trace_vals['state_msg'] = trace_message
        self.env['marketing.trace'].search([
            ('participant_id', 'in', self.ids),
            ('state', '=', 'scheduled'),
        ]).write(trace_vals)

    def action_set_running(self):
        self.write({'state': 'running', 'completion_date': False})

    def action_set_unlink(self):
        self.write({'state': 'unlinked'})
        self.env['marketing.trace'].search([
            ('participant_id', 'in', self.ids),
            ('state', '=', 'scheduled'),
        ]).write({
            'state': 'canceled',
            'state_msg': _('Record deleted'),
        })
        return True
