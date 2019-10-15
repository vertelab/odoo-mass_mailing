# -*- coding: utf-8 -*-
##############################################################################
#
# OpenERP, Open Source Management Solution, third party addon
# Copyright (C) 2004-2019 Vertel AB (<http://vertel.se>).
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
from datetime import datetime
import werkzeug
import pytz
import re

import logging
_logger = logging.getLogger(__name__)

# ~ [2221] Nyhetsbrev - Länk till webbaserat nyhetsbrev
# ~ [2222] Nyhetsbrev - Token-skydd till webbaserat nyhetsbrev
# ~ [2223] Nyhetsbrev - Arkiv under Mitt konto till webbaserade nyhetsbrev
# ~ [2221] [2222] [2223] Nyhetsbrev - Länk, Token, Arkiv
class website_massmailing(http.Controller):

    @http.route(['/mass_mailing/<int:mail_id>/token/<token>'], type='http', auth='public', website=True)
    def view_mail_token(self, mail_id, token,**post):
        mail = request.env['mail.mass_mailing'].sudo().browse(mail_id)
        if token == mail.token:
            return request.render('website_mass_mailing.mail', { 'mail':mail })
        else:
            return request.website.render('website.403', {})

    @http.route(['/mass_mailing/<int:mail_stat_id>/<token>/index.html'], type='http', auth='public', website=True)
    def view_mail_stat(self, mail_stat_id, token,**post):
        mail_mail_stats = request.env['mail.mail.statistics'].sudo().search([('mail_mail_id_int', '=', mail_stat_id)])
        mail_mail_stats.set_opened(mail_mail_ids=[mail_mail_stats])

        if token == mail_mail_stats.mass_mailing_id.token:
            return request.render('website_mass_mailing.mail', { 'mail':mail_mail_stats.mass_mailing_id })
        else:
            return request.website.render('website.403', {})

    @http.route('/mass_mailing/read_letter/<int:mail_mail_statistics_id>/letter.html', type='http', auth='none', website=True)
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




