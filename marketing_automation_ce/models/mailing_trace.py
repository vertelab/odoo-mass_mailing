# -*- coding: utf-8 -*-
# Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class MailingTrace(models.Model):
    _inherit = 'mailing.trace'

    marketing_trace_id = fields.Many2one(
        'marketing.trace', string='Marketing Trace', index=True,
        ondelete='cascade')

    def _marketing_traces(self, traces):
        """Return the marketing traces linked to the given mailing traces."""
        return traces.filtered(
            lambda t: t.marketing_trace_id
            and t.marketing_trace_id.activity_type == 'email'
        ).marketing_trace_id

    def set_clicked(self, domain=None):
        traces = super().set_clicked(domain=domain)
        for marketing_trace in self._marketing_traces(traces):
            marketing_trace.process_event('mail_click')
        return traces

    def set_opened(self, domain=None):
        traces = super().set_opened(domain=domain)
        for marketing_trace in self._marketing_traces(traces):
            marketing_trace.process_event('mail_open')
        return traces

    def set_replied(self, domain=None):
        traces = super().set_replied(domain=domain)
        for marketing_trace in self._marketing_traces(traces):
            marketing_trace.process_event('mail_reply')
        return traces

    def set_bounced(self, domain=None, bounce_message=False):
        traces = super().set_bounced(
            domain=domain, bounce_message=bounce_message)
        for marketing_trace in self._marketing_traces(traces):
            marketing_trace.process_event('mail_bounce')
        return traces
