import os
import unittest

# Defaults in the production script are 25% profit + 19% VAT.
import sync_activeshop_to_plenty as sync


class PriceLogicTests(unittest.TestCase):
    def test_known_price_15_32(self):
        self.assertEqual(sync.calculate_sales_price(15.32), 22.79)

    def test_known_price_266_97(self):
        self.assertEqual(sync.calculate_sales_price(266.97), 397.12)

    def test_sales_price_relation_and_value(self):
        variation = {
            "variationSalesPrices": [
                {"salesPriceId": 7, "price": 20.00},
                {"salesPriceId": 8, "price": 22.79},
            ]
        }
        relation = sync.get_plenty_sales_price_relation(variation, 8)
        self.assertIsNotNone(relation)
        self.assertEqual(sync.get_plenty_sales_price(variation, 8), 22.79)

    def test_missing_sales_price(self):
        variation = {"variationSalesPrices": [{"salesPriceId": 7, "price": 20.0}]}
        self.assertIsNone(sync.get_plenty_sales_price(variation, 8))

    def test_cloudflare_challenge_detection(self):
        import requests
        response = requests.Response()
        response.status_code = 403
        response._content = b"<html><title>Just a moment...</title><script src='https://challenges.cloudflare.com/x'></script></html>"
        response.headers["Server"] = "cloudflare"
        self.assertTrue(sync.is_activeshop_cloudflare_challenge(response))

    def test_non_cloudflare_403_not_detected_as_challenge(self):
        import requests
        response = requests.Response()
        response.status_code = 403
        response._content = b'{"message":"Forbidden"}'
        self.assertFalse(sync.is_activeshop_cloudflare_challenge(response))


if __name__ == "__main__":
    unittest.main()
