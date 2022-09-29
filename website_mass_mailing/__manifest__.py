# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2022- Vertel AB (<https://vertel.se>).
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
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
# ~ [1927] Nyhetsbrev - Funktion för att läsa nyhetsbrev när det inte fungerar i mailklienten

{
    'name': 'Mass Mailing: Website Mailing',
    'version': '14.0.0.0.0',
    # Version ledger: 14.0 = Odoo version. 1 = Major. Non regressionable code. 2 = Minor. New features that are regressionable. 3 = Bug fixes
    'summary': 'Mass mail to partners, for view i browser',
    'category': 'Administration',
    'description': """
* Mass mail to partners, for view i browser
# Please check if this module can substitue - https://github.com/OCA/social/tree/11.0/mail_browser_view or https://github.com/vertelab/odoo-mail/tree/Dev-12.0/mail_browser_view
====================================
""",
    #'sequence': '1',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-mass_mailing/website_mass_mailing',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-mass_mailing',
    'depends': ['mass_mailing','website'],
    'data': [
        'views/template.xml',
        'views/mass_mailing.xml',
    ],
    'installable': True,
    'auto_install': True,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
