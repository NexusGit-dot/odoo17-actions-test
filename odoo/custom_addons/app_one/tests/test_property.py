from odoo.tests.common import TransactionCase


class TestProperty(TransactionCase):

    def test_create_property(self):
        prop = self.env['property'].create({
            'name': 'Villa',
            'expected_price': 250000.0,
            'garden': True,
        })
        self.assertTrue(prop.id)
        self.assertEqual(prop.name, 'Villa')
        self.assertEqual(prop.expected_price, 250000.0)
        self.assertTrue(prop.garden)

    def test_garden_orientation_selection(self):
        prop = self.env['property'].create({
            'name': 'Flat',
            'garden_orientation': 'south',
        })
        self.assertEqual(prop.garden_orientation, 'south')
        selection_keys = [key for key, _label in prop._fields['garden_orientation'].selection]
        self.assertIn(prop.garden_orientation, selection_keys)

    def test_search_property_by_name(self):
        self.env['property'].create({'name': 'Penthouse'})
        properties = self.env['property'].search([('name', '=', 'Penthouse')])
        self.assertEqual(len(properties), 1)
        self.assertEqual(properties.name, 'Penthouse')
