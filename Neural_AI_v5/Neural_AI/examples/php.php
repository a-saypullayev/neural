<?php
// Requires the PHP cURL extension.
$baseUrl = getenv("NEURAL_BASE_URL") ?: "http://127.0.0.1:8000";
$apiKey = getenv("NEURAL_API_KEY");

$payload = json_encode([
    "model" => "neural-1",
    "messages" => [["role" => "user", "content" => "Say hello in five words."]],
]);

$ch = curl_init("$baseUrl/v1/chat/completions");
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => $payload,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 120,
    CURLOPT_HTTPHEADER => ["Authorization: Bearer $apiKey", "Content-Type: application/json"],
]);
$body = curl_exec($ch);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$data = json_decode($body, true);
if ($status !== 200) {
    fwrite(STDERR, "Error $status: " . ($data["error"]["message"] ?? "unknown") . "\n");
    exit(1);
}
echo $data["choices"][0]["message"]["content"] . "\n";
