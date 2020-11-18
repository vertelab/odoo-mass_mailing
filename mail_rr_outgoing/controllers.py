# -*- coding: utf-8 -*-
from openerp import http

# class MailRoundRobin(http.Controller):
#     @http.route('/mail_rr_outgoing/mail_rr_outgoing/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/mail_rr_outgoing/mail_rr_outgoing/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('mail_rr_outgoing.listing', {
#             'root': '/mail_rr_outgoing/mail_rr_outgoing',
#             'objects': http.request.env['mail_rr_outgoing.mail_rr_outgoing'].search([]),
#         })

#     @http.route('/mail_rr_outgoing/mail_rr_outgoing/objects/<model("mail_rr_outgoing.mail_rr_outgoing"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('mail_rr_outgoing.object', {
#             'object': obj
#         })
