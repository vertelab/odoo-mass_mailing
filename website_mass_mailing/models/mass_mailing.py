# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution, third party addon
#    Copyright (C) 2004-2017 Vertel AB (<http://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning, RedirectWarning
import random
import string

import logging
_logger = logging.getLogger(__name__)

# ~ [2222] Nyhetsbrev - Token-skydd till webbaserat nyhetsbrev
class mass_mailing(models.Model):
    _inherit = 'mail.mass_mailing'
    
    @api.model
    def _get_token(self):
        return  ''.join([random.choice(string.ascii_letters + string.digits) for n in xrange(12)])

    token = fields.Char(string='Token',default=lambda t: t._get_token())

class MailMail(models.Model):
    _inherit = 'mail.mail'
    
    # ~ @api.one
    # ~ def send_get_mail_body(self, partner=None, context=None):
        # ~ """Return a specific ir_email body. The main purpose of this method
        # ~ is to be inherited to add custom content depending on some module."""
        # ~ _logger.warn('\n\n\n\n self %s' % self)
        # ~ body = super(MailMail, self).send_get_mail_body(partner=partner)
        # ~ _logger.warn('\n\n\n\n body %s' % body)
        # ~ return body.replace('#website_token#', _('<a href="%s/mass_mailing/%s/%s/index.html">View Web Version</a>') %(self.env['ir.config_parameter'].get_param('web.base.url'), mail.id, mail.mass_mailing_id.token))

    @api.model
    def send_get_mail_body(self, mail, partner=None):
        """ Override to add the full website version URL to the body. """
        body = super(MailMail, self).send_get_mail_body(mail, partner=partner)
        _logger.warn('\n\n\n\n body %s' % body)
        return body.replace('#xxxx_token#', _('<a href="%s/mass_mailing/%s/%s/index.html">View Web Version</a>') %(self.env['ir.config_parameter'].get_param('web.base.url'), mail.id, mail.mailing_id.token))
        # ~ if mail.model != 'mail.mass_mailing.contact' and partner:
            # ~ return body.replace('$website_consent', _('<a href="%s/mail/consent/%s/partner/%s">Click here to review this consent</a><br/>') %(self.env['ir.config_parameter'].get_param('web.base.url'), mail.mailing_id.id, partner.id))
        # ~ else:
            # ~ return body

