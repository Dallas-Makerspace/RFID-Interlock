// Only modify this file to include
// - function definitions (prototypes)
// - include files
// - extern variable definitions
// In the appropriate section

#ifndef PowerInterlock_H_
#define PowerInterlock_H_
#include "Arduino.h"
//add your includes for the project PowerInterlock here


//end of add your includes here
#ifdef __cplusplus
extern "C" {
#endif
void loop();
void setup();
#ifdef __cplusplus
} // extern "C"
#endif

boolean readRFID();
void convertRFID();
boolean serverRequest();
boolean readServerResponse();
void enableTiming();
void disableTiming();
void parseResponse();
boolean checkButton();

void turnOn();
void turnOff();

boolean currentOn();

//Do not add code below this line
#endif /* PowerInterlock_H_ */
