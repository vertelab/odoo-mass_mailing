# -*- coding: utf-8 -*-
##############################################################################
#
# OpenERP, Open Source Management Solution, third party addon
# Copyright (C) 2004-2015 Vertel AB (<http://vertel.se>).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning, RedirectWarning
from openerp import http
from openerp.http import request
from openerp import SUPERUSER_ID
import openerp.tools
import string
import werkzeug
import logging
_logger = logging.getLogger(__name__)


class MailMailStats(models.Model):
    _inherit = "mail.mail.statistics"



    @api.onchange('model','res_id')
    def _model_change(self):
        if self.model and self.res_id and self.env[self.model].browse(self.res_id):
            self.model_record = self.env[self.model].browse(self.res_id)

    #~ @api.model
    #~ def _select_objects(self):
        #~ #_logger.info('Select %s' % [(m.model, m.name) for m in self.env['ir.model'].search([])])
        #~ return [(m.model, m.name) for m in self.env['ir.model'].search([])] + [('', '')]
    #~ id_object = fields.Selection(selection='_select_objects',string='Model',)


    @api.one
    def _model_record(self):
        if self.model and self.res_id and self.env[self.model].browse(self.res_id):
            self.model_record = self.env[self.model].browse(self.res_id)

    @api.model
    def _reference_models(self):
        models = self.env['ir.model'].search([('state', '!=', 'manual')])
#        return self.env[self.model].browse(self.res_id)
        return [(model.model, model.name)
                for model in models
                if not model.model.startswith('ir.')]
    model_record = fields.Reference(string="Record",selection="_reference_models",compute="_model_record")

    @api.one
    def set_page_read(mail_mail_statistics_id):
        pass

class MassMailing(models.Model):
    _inherit = 'mail.mass_mailing'

    page = fields.Many2many(comodel_name='ir.ui.view', string='Page')


class res_partner(models.Model):
    _inherit = "res.partner"

    @api.one
    def _mass_mail_count(self):
        self.mass_mail_count = len(self.env['mail.mail.statistics'].search([('res_id','=',self.id),('model','=','res.partner')]))
    mass_mail_count = fields.Integer(compute="_mass_mail_count")


class massMailRead(http.Controller):

    @http.route('/mail/read_letter/<int:mail_mail_statistics_id>/letter.html', type='http', auth='none')
    def read_letter(self, mail_mail_statistics_id, **post):
        mail_mail_stats = request.env['mail.mail.statistics'].sudo().search([('mail_mail_id_int', '=', mail_mail_statistics_id)])
        mail_mail_stats.set_opened(mail_mail_ids=[mail_mail_stats])
        response = werkzeug.wrappers.Response()
        response.mimetype = 'text/html'
        response.data = mail_mail_stats.mass_mailing_id.body_html
        return response

    @http.route('/mail/page/<int:mail_mail_statistics_id>/index.html', type='http', auth='none')
    def read_page(self, mail_mail_statistics_id, **post):
        mail_mail_stats = request.env['mail.mail.statistics'].browse(int(mail_mail_statistics_id))
        mail_mail_stats.set_page_read(mail_mail_statistics_id) #new method that calculate who read this page
        template = request.env['mail.mail.statistics'].browse(mail_mail_statistics_id).mass_mailing_id.page.xml_id
        return request.render(template, {'path': '/mail/page/%s/index.html' %mail_mail_statistics_id})

