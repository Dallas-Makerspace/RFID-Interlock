//TODO
/* Add changes from this url
 * http://www.gumbolabs.org/2009/10/17/parallax-rfid-reader-arduino/
 * he address the funky parallax behavior
 */

// Do not remove the include below
#include "PowerInterlock.h"
#include <SoftwareSerial.h>
#include <SPI.h>
#include <Ethernet.h>

#define RFID_ENABLE 2
#define RFID_SERIAL_TX 9
#define RFID_SERIAL_RX 8
#define RFID_LENGTH 10
#define RFID_START_CHAR 0x0A
#define RFID_END_CHAR 0x0D

#define DEVICE_PIN 3
#define BUTTON_PIN 4

#define TIMEOUT 2000
#define SERVER_WAIT_TIME 2000
#define RESPONSE_BUFFER 400
#define COMMAND_BUFFER 400
#define STRING_BUFFER 150

char rfidCode[RFID_LENGTH+RFID_LENGTH];
unsigned long rfid_long = 0;
SoftwareSerial RFID = SoftwareSerial(RFID_SERIAL_RX,RFID_SERIAL_TX);

byte mac[] = { 0x90, 0xA2, 0xDA, 0x0D, 0x38, 0x1B };
char server[] = "dallasmakerspace.org";
IPAddress ip(192,168,1,17);
byte dns1[] = {8,8,8,8};
EthernetClient client;

String url = "";
String cmd = "";

enum States { WAITING, READING_RFID, TIMER_COUNTDOWN, RFID_READ, SERVER_WAIT, ERROR, DENIED};
int state = WAITING;

long lastTime = 0;
long timerTime = 0;
boolean timing = false;

String response = "";
boolean authorized = false;
long authorizedTime = 0;

void setup()
{
	response.reserve(RESPONSE_BUFFER);
	url.reserve(STRING_BUFFER);
	cmd.reserve(COMMAND_BUFFER);

	Serial.begin(9600);
	Serial.println("PowerInterlock Start");
	turnOff();
	disableTiming();

	RFID.begin(2400);
	delay(500);

	pinMode(RFID_ENABLE, OUTPUT);
	//digitalWrite(RFID_ENABLE, LOW);
	pinMode(DEVICE_PIN, OUTPUT);

	Ethernet.begin(mac, ip, dns1);
	//After a couple hours, the DHCP started to fail for some reason
	/*if (Ethernet.begin(mac) == 0) {
		Serial.println("Failed to configure Ethernet using DHCP");
		Ethernet.begin(mac, ip);
	}*/
	// give the Ethernet shield a second to initialize:
	delay(1000);
}

void loop()
{
	if (timing) {
		timerTime += millis() - lastTime;
		lastTime = millis();
	}

	if (state == WAITING || state == TIMER_COUNTDOWN) {
		if (state == WAITING && timing) disableTiming();
		if (readRFID()) {
			//Serial.print("RFID: ");
			//Serial.println(rfidNum);

			convertRFID();
			if (serverRequest()) {
				state = SERVER_WAIT;
				enableTiming();
			}
			else state = WAITING;
		}
	}
	else if (state == SERVER_WAIT){
		//Serial.println(timerTime);
		if (timerTime < TIMEOUT) {
			if (readServerResponse()) {
				disableTiming();
				parseResponse();
				if (authorized) {
					state = TIMER_COUNTDOWN;
					turnOn();
				}
				else state = DENIED;
			}
		}
		else {
			state = WAITING;
		}
	}
	else if (state == DENIED) {
		Serial.println("DENIED");
		state = WAITING;
	}

	if (state == TIMER_COUNTDOWN && timing && currentOn()) {
		disableTiming();
	}
	else if (state == TIMER_COUNTDOWN && (!timing && !currentOn())) {
		enableTiming();
	}

	if (state == TIMER_COUNTDOWN) {
		if ((timing && (timerTime > authorizedTime)) || checkButton()) {
			state = WAITING;
			disableTiming();
			turnOff();
		}
	}

	/*if (timerTime > 0)
		Serial.println(timerTime);*/
}

boolean readRFID() {
	//if (RFID.available()) RFID.flush();
	digitalWrite(RFID_ENABLE, LOW);    // Activate the RFID reader
	
	for (byte i = 0; i < RFID_LENGTH; i++)
		rfidCode[i] = 0;

	if (RFID.available()) {
		int val = RFID.read();
		Serial.print(val);

		if (val == RFID_START_CHAR) {
			RFID.readBytes(rfidCode, RFID_LENGTH);

			Serial.print("RFID Read: ");
			Serial.println(rfidCode);

			digitalWrite(RFID_ENABLE, HIGH);   // deactivate the RFID reader for a moment so it will not flood
			RFID.flush();                      // clear the buffer
			delay(1500);                       // wait for a bit

			return true;
		 }
	}
	return false;
}

//turn rfid from 10byte hex ascii to decimal long
void convertRFID() {
	rfid_long = 0;
	char temp[8]; //copy to temp we only want the first 2 values
	for (int i = 0; i < 8; i++)
		temp[i] = (char)rfidCode[i+2];
	rfid_long = strtoul(temp, NULL, 16);
}

//builds the url for the api request, connects to the server, and sends the request
boolean serverRequest() {
	//Serial.print(server);
	//Serial.println(page);
	client.stop();

	Serial.println("connecting...");
	if (client.connect(server, 80)) {
		Serial.println("connected");
		client.print("GET /makermanager/index.php?r=api/toolValidate&badge=");
		client.print(rfid_long);
		client.print("&tool=1");
		client.println(" HTTP/1.1");
		client.print("Host: ");
		client.println(server);
		client.println("User-Agent: arduino-ethernet");
		client.println("Connection: close");
		client.println("");
		
		//Serial.println(cmd);
		//client.println(cmd);
		return true;
	}
	else {
		Serial.println("connection failed");
		return false;
	}
}

boolean readServerResponse() {
	response = "";
	char inBuf[RESPONSE_BUFFER];

	//response.reserve(RESPONSE_BUFFER);
	int bytesRead = 0;
	if (client.connected()) {
		delay(SERVER_WAIT_TIME);
		Serial.println("awaiting response");
		while (client.available()) {
			char c = client.read();
			Serial.print(c);
			if (bytesRead < RESPONSE_BUFFER) inBuf[bytesRead] = c;
			//else client.flush();
			bytesRead++;
		}
		if (bytesRead > 0) {
			response = inBuf;
			Serial.println("Response Received");
			//if (!client.connected()) client.stop();
			return true;
		}
	}
	return false;
}

void enableTiming() {
	timerTime = 0;
	timing = true;
	lastTime = millis();
	//Serial.println("timer on");
}

void disableTiming() {
	timerTime = 0;
	timing = false;
	lastTime = millis();
	//Serial.println("timer off");
}

void parseResponse() {
	Serial.println("Parsing Response");
	
	//finds index of authorized and looks for the 't' in true
	int ind = response.indexOf("authorized");
	if (ind >= 0) {
		ind += 12;
		//Serial.println(response.charAt(ind));
		if (response.charAt(ind) == 't') {
			authorized = true;
			Serial.println("User is authorized");
		}
		else authorized = false;
	}
	else authorized = false;
	
	//finds start and end of the number after timeout
	ind = response.indexOf("timeout");
	if (ind >= 0) {
		ind += 9;
		//String responseTimer = response.substring(ind);
		int endInd = ind;
		Serial.println(response.charAt(ind));
		for (int i = ind; i < (int)response.length(); i++) {
			if (isDigit(response.charAt(i))) endInd++;
			else break;
		}
		Serial.println(response.charAt(endInd));
		Serial.print("Substring: ");
		Serial.println(response.substring(ind, endInd));
		authorizedTime = response.substring(ind, endInd).toInt() * 1000;	//server sends seconds so convert to millis
		Serial.print("Timeout: ");
		Serial.println(authorizedTime);
	}
	else authorizedTime = 0;
	response = "";
}

void turnOn() {
	Serial.print("Device On: ");
	Serial.println(millis());
	if (authorizedTime > 0) enableTiming();
	digitalWrite(DEVICE_PIN, HIGH);
}

void turnOff() {
	Serial.print("Device Off: ");
	Serial.println(millis());
	digitalWrite(DEVICE_PIN, LOW);
}

//stub for button pressed check and debouncing to use for immediate stop
boolean checkButton() {
	return false;
}

//checks to see if the current is on using the current detecting circuit
boolean currentOn() {
	//return false;
	int sensorPeak = 0;
	int sensorValue = 0;
	for (int i = 0;  i < 20; i++) {
		sensorValue = analogRead(A0);
		if (sensorValue > sensorPeak) {
			sensorPeak = sensorValue;
		}
		delay(1);
	}
	//Serial.println(sensorPeak);
	if (sensorPeak > 514) {
		// Device ON
		//Serial.println("Device ON");
		return true;
	} else {
		// Device OFF
		//Serial.println("Device OFF");
		return false;
	}
}
