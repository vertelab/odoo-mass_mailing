# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MailingMailing(models.Model):
    _inherit = 'mailing.mailing'

    use_in_marketing_automation = fields.Boolean(
        string='Specific mailing used in marketing campaign', default=False,
        help="Marketing campaigns use mass mailings with specific behaviour; "
             "this field marks a mailing as belonging to a flow so its "
             "statistics are reported per activity instead of in the mass "
             "mailing report.")
    marketing_activity_ids = fields.One2many(
        'marketing.activity', 'mass_mailing_id', string='Marketing Activities',
        copy=False)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if 'subject' in fields_list \
                and self.env.context.get('default_use_in_marketing_automation'):
            vals['subject'] = self.env.context.get('default_name')
        return vals

    def _get_link_tracker_values(self):
        res = super()._get_link_tracker_values()
        if self.env.context.get('default_marketing_activity_id'):
            activity = self.env['marketing.activity'].browse(
                self.env.context['default_marketing_activity_id'])
            res['campaign_id'] = activity.campaign_id.utm_campaign_id.id
            res['source_id'] = activity.source_id.id
        return res

    def _get_seen_list_extra(self):
        return (
            'LEFT JOIN marketing_trace m ON (s.marketing_trace_id = m.id)',
            'AND (m.is_test IS NULL OR m.is_test = false)',
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_if_no_linked_activities(self):
        protected = self.filtered(lambda m: m.marketing_activity_ids)
        if protected:
            raise UserError(_(
                "Mailings %(names)s are used in marketing campaigns. You "
                "should take care of this before unlinking the mailings.",
                names=", ".join(protected.mapped("name"))))
