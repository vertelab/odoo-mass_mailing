#!/usr/bin/env python3
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

# TODO : Prune unnecessary imports
#import base64
#import re
#
#from openerp import tools
#from openerp import SUPERUSER_ID
from openerp.osv import osv
#from openerp.osv import fields
#from openerp.tools.safe_eval import safe_eval as eval
#from openerp.tools.translate import _

import logging
from openerp import api, fields, models, tools

_logger = logging.getLogger(__name__)

class mail_compose_message_rr(osv.TransientModel): # Should be changable to models.TransientModel
    """
    Simple extension of mail.compose.message made to give more control of
    used outgoing mailservers.
    """
    _inherit = 'mail.compose.message'
    _description = 'Email composition wizard rotating between valid outgoing mail servers'
    @api.model
    def get_mail_values(self,wizard, res_ids, context=None):
        """Generate the values that will be used by send_mail to create mail_messages
        or mail_mails."""
        results = super(mail_compose_message_rr, self).get_mail_values(
                                         wizard, res_ids, context=None)
        # Let default system select mail-server if given single res_id or less
        if len(res_ids) <= 1:
            _logger.warn("MyTag:: 1 or less mails to send.")
            return results
	# else:

        # Simple test logging
        _logger.warn("MyTag:: Got here. Number of IDs: {}".format(len(res_ids)))
        for res_id in res_ids:
            _logger.warn("MyTag:: Got into loop. Number of ID: {}".format(res_id))
        
        # Assign mail server to mail 
        mail_servers = self.env['ir.mail_server'].search([
                                                       ('active', '=', 'True' )
                                                   ])
        nbr_of_servers = len(mail_servers)
        curr_server_index = 0
        for res_id in res_ids:
            if "mail_server_id" not in results[res_id]:
                results[res_id]["mail_server_id"] = mail_servers[curr_server_index].id
                curr_server_index = (curr_server_index+1) %  nbr_of_servers
                _logger.warn("MyTag:: Mail server index: {}".format(curr_server_index))
                _logger.warn("MyTag:: Current mail server: {}".format(mail_servers[curr_server_index]))
                _logger.warn("MyTag:: Current mail server id: {}".format(mail_servers[curr_server_index].id))          
        return results
