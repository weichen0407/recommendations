from recommendation_contents.llm import format_llm_error


class ProviderError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def test_llm_error_reports_status_without_exposing_provider_message():
    error = ProviderError("secret-api-key https://private-provider.example", 429)

    result = format_llm_error(error)

    assert "ProviderError, HTTP 429" in result
    assert "fewer workers" in result
    assert "secret-api-key" not in result
    assert "private-provider" not in result


def test_llm_error_explains_payment_required():
    result = format_llm_error(ProviderError("provider details", 402))

    assert "HTTP 402" in result
    assert "quota/billing authorization" in result
