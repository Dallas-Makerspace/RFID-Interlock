#include <Wiegand.h>
#include <SPI.h>
#include <HttpClient.h>
#include <Ethernet.h>
#include <EthernetClient.h>

WIEGAND rfid;

// Enter a MAC address for your controller below.
// Newer Ethernet shields have a MAC address printed on a sticker on the shield
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };

const char server[] = "192.168.0.100";
//const char server[] = "www.google.com";

const char script[] = "/test.php?device=12";

EthernetClient client;

// 0 = off
// 1 = on
int interlockState = 0;
int err = 0;
char uri[32];

const int ledPin =  9;
const int stopButtonPin = 8;
const int buzzerPin = 5;
const int relayPin = 7;

void setup() {
  // Starting boot-up
  tone(buzzerPin, 1568, 400);
  delay(400);
  noTone(buzzerPin);
  
  Serial.begin(9600);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for Leonardo only
  }
  
  // start the Ethernet connection:
  while (Ethernet.begin(mac) == 0) {
    Serial.println("Failed to configure Ethernet using DHCP");
    Serial.println("Sleeping for 5 seconds");
    delay(5000);
  }
  
  Serial.println("Connected via DHCP");
  
  // give the Ethernet shield a second to initialize:
  delay(1000);

  // initialize the LED pin as an output:
  pinMode(ledPin, OUTPUT);
  pinMode(relayPin, OUTPUT);
  
  // initialize the button pin as an input:
  pinMode(stopButtonPin, INPUT);
  
  // turn on pullup resistors
  digitalWrite(stopButtonPin, HIGH); 
    
  // Start RFID reader
  rfid.begin();
  
  // Tell the world we're ready
  allowTone();
}

void loop() {
  int buttonState = digitalRead(stopButtonPin);
  if (interlockState == 1 && buttonState == LOW) {
    deactivate();
  } else {
    if(rfid.available()) {
      unsigned long tag = rfid.getCode();
    
      Serial.print("Wiegand HEX = ");
      Serial.print(tag,HEX);
      Serial.print(", DECIMAL = ");
      Serial.print(tag);
      Serial.print(", Type W");
      Serial.println(rfid.getWiegandType());

      Serial.println("Checking server for authorization.");
      sprintf(uri, "%s&tag=%lu", script, tag);
    
      EthernetClient c;
      HttpClient http(c);
      err = http.get(server, uri);
      if (err == 0) {
        err = http.responseStatusCode();
        if (err == 204) {
          err = http.skipResponseHeaders();
          if (err >= 0) {
            Serial.println("Authorized!");
            activate();
            allowTone();
          } else {
            Serial.print("Failed to skip response headers: ");
            Serial.println(err);
            deactivate();
          }
        } else {
          Serial.print("Getting response failed: ");
          Serial.println(err);
          denyTone();
          deactivate();
        }
      } else {
        Serial.print("Connection failed: ");
        Serial.println(err);
        deactivate();
      }
      http.stop();
    }
  }
}

void activate()
{
  interlockState = 1;
  digitalWrite(ledPin, HIGH);
  digitalWrite(relayPin, HIGH);
  Serial.println("Device activated!");
}

void deactivate()
{
  interlockState = 0;
  digitalWrite(ledPin, LOW);
  digitalWrite(relayPin, LOW);
  Serial.println("Device de-activated!");

  Serial.println("Notifying server of device shutdown.");

  sprintf(uri, "%s&status=shutdown", script);

  EthernetClient c;
  HttpClient http(c); 
  err = http.get(server, uri);

  if (err == 0) {
    err = http.responseStatusCode();
    if (err == 200) {
      Serial.println("Notified server of device shutdown.");
    } else {    
      Serial.print("Getting response failed: ");
      Serial.println(err);
    }
  } else {
    Serial.print("Connection failed: ");
    Serial.println(err);
  }
  http.stop();
}

void denyTone()
{
  digitalWrite(ledPin, HIGH);
  tone(buzzerPin, 262, 200);
  delay(200);
  digitalWrite(ledPin, LOW);
  tone(buzzerPin, 262, 200);
  delay(200);
  digitalWrite(ledPin, HIGH);
  tone(buzzerPin, 262, 600);
  delay(600);
  digitalWrite(ledPin, LOW);
  noTone(buzzerPin);
}

void allowTone()
{
  tone(buzzerPin, 262, 200);
  delay(200);
  tone(buzzerPin, 262, 200);
  delay(200);
  tone(buzzerPin, 1568, 400);
  delay(400);
  noTone(buzzerPin);
}
