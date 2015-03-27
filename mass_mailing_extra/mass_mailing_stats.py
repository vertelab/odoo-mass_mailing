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

    @api.one
    def _model_name(self):
        if self.env.get('self.model'):
            model = self.env[self.model].browse(self.res_id) if self.model else False
        self.model_name = model.name if model else _('None')

    model_name = fields.Char(compute="_model_name")
    
    model_id = fields.Many2one(comodel_name="ir.model")
    

    @api.one
    def _model_id(self):
        if self.env.get('self.model'):
            model = self.env[self.model].browse(self.res_id) if self.model else False
        self.model_id = model if model else False

    model_id = fields.Many2one(comode_name="self.model",compute="_model_id")
