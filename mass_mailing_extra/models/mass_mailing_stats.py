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
    visited_us = fields.Datetime(string='Visited Us', help='Date when email receiver visite our site first time')

    @api.one
    def set_page_read(self, mail_mail_ids=None, mail_message_ids=None): #method that calculate who visited our page
        stat_ids = self._get_ids(self, mail_mail_ids, mail_message_ids, [('visited_us', '=', False)])
        self.write(self, stat_ids, {'visited_us': fields.datetime.now()})
        return stat_ids

class MassMailing(models.Model):
    _inherit = 'mail.mass_mailing'

    # ~ page = fields.Many2one(comodel_name='ir.ui.view', string='Page')

    @api.one
    def _visited_us(self):
        self.visited_us = self.env['mail.mail.statistics'].search_count([('visited_us', '!=', False)])
        statistics_count = self.env['mail.mail.statistics'].search_count([])
        if statistics_count != 0:
            self.visited_us_ratio = self.visited_us / statistics_count * 100.0
        else:
            self.visited_us_ratio = 0
    visited_us = fields.Integer(string='Visited Us', compute='_visited_us')
    visited_us_ratio = fields.Integer(string='Visited Ratio', compute='_visited_us')


class res_partner(models.Model):
    _inherit = "res.partner"

    @api.one
    def _mass_mail_count(self):
        self.mass_mail_count = self.env['mail.mail.statistics'].search_count([('res_id','=',self.id),('model','=','res.partner')])
    mass_mail_count = fields.Integer(compute="_mass_mail_count")


class MailMail(models.Model):
    _inherit = 'mail.mail'

    @api.model
    def send_get_mail_body(self, mail, partner=None):
        """ Override to add the full website version URL to the body. """
        body = super(MailMail, self).send_get_mail_body(mail, partner=partner)
        return body.replace('$website_url', _('<a href="%s/mail/page/%s/index.html">View Web Version</a>') %(self.env['ir.config_parameter'].get_param('web.base.url'), mail.id))


class massMailRead(http.Controller):

    @http.route('/mail/read_letter/<int:mail_mail_statistics_id>/letter.html', type='http', auth='none', website=True)
    def read_letter(self, mail_mail_statistics_id, **post):
        mail_mail_stats = request.env['mail.mail.statistics'].sudo().search([('mail_mail_id_int', '=', mail_mail_statistics_id)])
        mail_mail_stats.set_opened(mail_mail_ids=[mail_mail_stats])
        template_data = request.env['email.template'].sudo().render_template(mail_mail_stats.mass_mailing_id.body_html, 'mail.mail.statistics', mail_mail_stats.id) #(template, model, record.id)
        response = werkzeug.wrappers.Response()
        response.mimetype = 'text/html'
        response.data = '''<!doctype html>
        <html lang="sv-se">
            <head>
                <meta charset="utf-8" />
                <title>''' + mail_mail_stats.mass_mailing_id.name + '''</title>
                <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/3.2.0/css/bootstrap.min.css"/>
            </head>
            <body>
        ''' + template_data + '''
                <script type="text/javascript" src="https://maxcdn.bootstrapcdn.com/bootstrap/3.2.0/js/bootstrap.min.js"/>
            </body>
        </html>
        '''
        return response

    @http.route('/mail/page/<int:mail_mail_statistics_id>/index.html', type='http', auth='none', website=True)
    def read_page(self, mail_mail_statistics_id, **post):
        mail_mail_stats = request.env['mail.mail.statistics'].sudo().search([('mail_mail_id_int', '=', mail_mail_statistics_id)])
        mail_mail_stats.visited_us = fields.Datetime.now()
        return mail_mail_stats.mass_mailing_id.body_html.replace('$website_url', '')
        # ~ mail_mail_stats.set_page_read(mail_mail_ids=[mail_mail_stats])
        # ~ template = mail_mail_stats.mass_mailing_id.page.xml_id
        # ~ return request.website.render(template, {'path': '/mail/page/%s/index.html' %mail_mail_stats.mail_mail_id_int})
