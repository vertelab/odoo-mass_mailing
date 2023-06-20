import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class PropertyStakeholderMailing(models.Model):
     _inherit = 'property.stakeholder'
     _mailing_enabled = True

