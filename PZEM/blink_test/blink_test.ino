// Minimal board sanity test — no TFT, no PZEM.
// If Serial prints a counter and the LED-side sign of life shows,
// the board + cable + USB driver + upload path all work.

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n\n=== BLINK TEST BOOTED ===");
}

int n = 0;
void loop() {
  Serial.printf("alive %d\n", n++);
  delay(500);
}
