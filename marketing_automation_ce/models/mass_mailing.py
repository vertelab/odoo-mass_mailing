# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _


_logger = logging.getLogger(__name__)


class MassMailingCampain(models.Model):
     _inherit = 'utm.campaign'

     model_id = fields.Many2one(                                                                                                         
        'ir.model', string='Model', index=True, required=True,ondelete="no action",                                                                          
        default=lambda self: self.env.ref('base.model_res_partner', raise_if_not_found=False),                                          
        domain="['&', ('is_mail_thread', '=', True), ('model', '!=', 'mail.blacklist')]")                                               
     model_name = fields.Char(string='Model Name', related='model_id.model', readonly=True, store=True)
     mailing_activity_ids = fields.Many2many(comodel_name='mailing.mailing')


class MassMailing(models.Model):
    _inherit = 'mailing.mailing'

     # Add reference to campains so we can show them in a treeview
    interval_number = fields.Integer(string='Send after', default=1)
    interval_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')], string='Delay Type',
        default='hours', required=True)
        
    @api.depends('interval_type', 'interval_number')
    def _compute_interval_standardized(self):
        factors = {'hours': 1,
                   'days': 24,
                   'weeks': 168,
                   'months': 720}
        for activity in self:
            activity.interval_standardized = activity.interval_number * factors[activity.interval_type]

    interval_standardized = fields.Integer('Send after (in hours)', compute='_compute_interval_standardized', store=True, readonly=True)

    validity_duration = fields.Boolean('Validity Duration')
    validity_duration_number = fields.Integer(string='Valid during', default=0)
    validity_duration_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')],
        default='hours', required=True)

    require_sync = fields.Boolean('Require trace sync')

    activity_type = fields.Selection([
        ('none', 'None'),
        ('email', 'Email'),
        ('action', 'Server Action')
        ], required=False, default='none')
    mass_mailing_id = fields.Many2one('mailing.mailing', string='Email Template')
    server_action_id = fields.Many2one('ir.actions.server', string='Server Action')

    # Related to parent activity
    parent_id = fields.Many2one(comodel_name='mailing.mailing', string='Activity',
        index=True, ondelete='cascade')
    child_ids = fields.One2many('mailing.mailing', 'parent_id', string='Child Activities')
    trigger_type = fields.Selection([
        ('begin', 'beginning of campaign'),
        ('act', 'another activity'),
        ('mail_open', 'Mail: opened'),
        ('mail_not_open', 'Mail: not opened'),
        ('mail_reply', 'Mail: replied'),
        ('mail_not_reply', 'Mail: not replied'),
        ('mail_click', 'Mail: clicked'),
        ('mail_not_click', 'Mail: not clicked'),
        ('mail_bounce', 'Mail: bounced')], default='begin', required=True)
