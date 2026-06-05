from app.services.stock_import.text_parser import parse_stock_text_file


def test_parse_stock_csv_with_headers():
    content = "Артикул;Количество\nF1002;12\nG2003;5\n".encode("utf-8")

    result = parse_stock_text_file(content, "stock.csv")

    assert result.non_empty_rows == 2
    assert result.rows[0].raw_article == "F1002"
    assert result.rows[0].raw_quantity == "12"
    assert result.rows[1].raw_article == "G2003"
    assert result.rows[1].raw_quantity == "5"


def test_parse_stock_text_without_headers_as_two_columns():
    content = "F1002\t12\nG2003\t5\n".encode("utf-8")

    result = parse_stock_text_file(content, "stock.txt")

    assert result.non_empty_rows == 2
    assert result.rows[0].raw_article == "F1002"
    assert result.rows[0].raw_quantity == "12"
    assert result.rows[1].raw_article == "G2003"
    assert result.rows[1].raw_quantity == "5"
