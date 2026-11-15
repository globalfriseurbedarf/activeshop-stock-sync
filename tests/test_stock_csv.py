import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import stock_sync as sync


class StockCsvTests(unittest.TestCase):
    def test_local_csv_is_authoritative_even_when_online_available(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "b2b-de.csv"
            file.write_text('sku;qty;price\n105379;19;11.74\n108616;4;13.45\n', encoding='utf-8')
            with patch.object(sync, 'FALLBACK_FEED_PATH', str(file)), \
                 patch.object(sync, 'FEED_SOURCE_MODE', 'local_first'), \
                 patch.object(sync.requests, 'get', side_effect=AssertionError('Online request must not run')):
                df = sync.download_feed()
            stock_map = sync.build_feed_stock_map(df)
            self.assertEqual(stock_map, {'105379': 19, '108616': 4})

    def test_more_than_300_products_not_truncated(self):
        df = pd.DataFrame([{'sku': str(100000+i), 'qty': str(i), 'price': '12.34'} for i in range(505)])
        result = sync.build_feed_stock_map(df)
        self.assertEqual(len(result), 505)
        self.assertEqual(result['100504'], 504)

    def test_missing_local_file_can_use_online_feed(self):
        class Response:
            content = b'sku;qty\n105379;7\n'
            def raise_for_status(self): pass
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / 'not-here.csv'
            with patch.object(sync, 'FALLBACK_FEED_PATH', str(missing)), \
                 patch.object(sync, 'FEED_SOURCE_MODE', 'local_first'), \
                 patch.object(sync.requests, 'get', return_value=Response()) as get:
                df = sync.download_feed()
            get.assert_called_once()
            self.assertEqual(sync.build_feed_stock_map(df)['105379'], 7)


if __name__ == '__main__':
    unittest.main()
