
# **Redfish Logging Filter Techniques**

Redfish provides different filter techniques that would help with getting the targeted logs.  This document provides some of the best-known methods that can be used for filtering log files. 

Please note that it is important to utilize these escape sequences when using curl 
- Use Double Quotes for the GET HTTPS Sequence 
- Use \ before using $ 
- Use & between multiple filters 
- Use %20 wherever there is space 

                                                                          
[[_TOC_]]

# Using $top filter
This filter is used for getting the number of entries as output 

##Example curl script:
**Example 1**:  Get the top 2 log entries 
```bash
curl -k -H "Content-Type: application/json" -u "admin":"admin" -X GET "https://localhost/redfish/v1/Managers/System/LogServices/EventLog/Entries?\$top=2"

Output: 
{
  "@odata.id": "/redfish/v1/Managers/System/LogServices/EventLog/Entries",
  "@odata.type": "#LogEntryCollection.LogEntryCollection",
  "Description": "Collection of System Event Log Entries",
  "Members": [
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745913763",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:02:43+00:00",
      "EntryType": "Event",
      "Id": "1745913763",
      "Message": "C2141   Board with serial number                  was installed.",
      "MessageArgs": [
        "C2141  ",
        "Board",
        "                "
      ],
      "MessageId": "OpenBMC.0.1. InventoryAdded",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    },
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745913763_1",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:02:43+00:00",
      "EntryType": "Event",
      "Id": "1745913763_1",
      "Message": "A2040   Board with serial number P651930340562039 was installed.",
      "MessageArgs": [
        "A2040  ",
        "Board",
        "P651930340562039"
      ],
      "MessageId": "OpenBMC.0.1.InventoryAdded",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    }
  ],
  "Members@odata.count": 39,
  "Members@odata.nextLink": "/redfish/v1/Managers/System/LogServices/EventLog/Entries?$skip=2",
  "Name": "System Event Log Entries"
}
```
Please note that the <I>Members@odata.nextLink</I> will provide the next offset to the next query,  if the $top is greater or equal to the <I>"Members@odata.count"</I> then you will see the <I>Members@odata.nextLink</I> will not appear in the output.

# Using $skip filter
This filter is used for skipping the number of log records, recommended to use it with <I>$top</I> as this will control the output

##Example curl script:
**Example 1**:  Skip 10 entries and ret the top 2 log entries 
```bash
curl -k -H "Content-Type: application/json" -u "admin":"admin" -X GET "https://localhost/redfish/v1/Managers/System/LogServices/EventLog/Entries?\$skip=10&\$top=2"

Output: 
{
  "@odata.id": "/redfish/v1/Managers/System/LogServices/EventLog/Entries",
  "@odata.type": "#LogEntryCollection.LogEntryCollection",
  "Description": "Collection of System Event Log Entries",
  "Members": [
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745913859",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:04:19+00:00",
      "EntryType": "Event",
      "Id": "1745913859",
      "Message": "Name:CPU sensor crossed a warning high threshold going low. Reading=Reading:49.783244 Threshold=Threshold:50.000000.",
      "MessageArgs": [
        "Name:CPU",
        "Reading:49.783244",
        "Threshold:50.000000"
      ],
      "MessageId": "OpenBMC.0.4.SensorThresholdWarningHighGoingLow",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    },
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745914464",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:14:24+00:00",
      "EntryType": "Event",
      "Id": "1745914464",
      "Message": "Discrete event POST_COMPLETE_TIMEOUT asserted",
      "MessageArgs": [
        "POST_COMPLETE_TIMEOUT"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    }
  ],
  "Members@odata.count": 39,
  "Members@odata.nextLink": "/redfish/v1/Managers/System/LogServices/EventLog/Entries?$skip=12",
  "Name": "System Event Log Entries"
}
```
Please note that the <I>Members@odata.nextLink</I> updated with the <I>$skip + $top</I> 

# Using $filter filter
This filter is used to filter a specific Redfish property. At present only equality (eq) is supported. 

##Example curl script:
**Example 1**:  Filter all the Log Entries whose Severity is "Warning"
```bash
curl -k -H "Content-Type: application/json"  -u "admin":"admin"  -X GET "https://localhost/redfish/v1/Managers/System/LogServices/EventLog/Entries?\$filter=Severity%0eq%20'Warning'"

Output: 
{
  "@odata.id": "/redfish/v1/Managers/System/LogServices/EventLog/Entries",
  "@odata.type": "#LogEntryCollection.LogEntryCollection",
  "Description": "Collection of System Event Log Entries",
  "Members": [
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745913805_4",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:03:25+00:00",
      "EntryType": "Event",
      "Id": "1745913805_4",
      "Message": "Name:CPU sensor crossed a warning high threshold going high. Reading=Reading:70.214780 Threshold=Threshold:50.000000.",
      "MessageArgs": [
        "Name:CPU",
        "Reading:70.214780",
        "Threshold:50.000000"
      ],
      "MessageId": "OpenBMC.0.4.SensorThresholdWarningHighGoingHigh",
      "Name": "System Event Log Entry",
      "Severity": "Warning"
    },
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1746429300",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-05T07:15:00+00:00",
      "EntryType": "Event",
      "Id": "1746429300",
      "Message": "Name:CPU sensor crossed a warning high threshold going high. Reading=Reading:66.261547 Threshold=Threshold:50.000000.",
      "MessageArgs": [
        "Name:CPU",
        "Reading:66.261547",
        "Threshold:50.000000"
      ],
      "MessageId": "OpenBMC.0.4.SensorThresholdWarningHighGoingHigh",
      "Name": "System Event Log Entry",
      "Severity": "Warning"
    },
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1747026964",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-12T05:16:04+00:00",
      "EntryType": "Event",
      "Id": "1747026964",
      "Message": "Name:CPU sensor crossed a warning high threshold going high. Reading=Reading:61.095589 Threshold=Threshold:50.000000.",
      "MessageArgs": [
        "Name:CPU",
        "Reading:61.095589",
        "Threshold:50.000000"
      ],
      "MessageId": "OpenBMC.0.4.SensorThresholdWarningHighGoingHigh",
      "Name": "System Event Log Entry",
      "Severity": "Warning"
    }
  ],
  "Members@odata.count": 3,
  "Name": "System Event Log Entries"
}
```
**Example 2**: Filter all the Log Entries whose MessageId is "OpenBMC.0.4.DiscreteEventAsserted".
```bash
curl -k -H "Content-Type: application/json"  -u "admin":"admin"  -X GET "https://localhost/redfish/v1/Managers/System/LogServices/EventLog/Entries?\$filter=MessageId20eq%20'OpenBMC.0.4.DiscreteEventAsserted'"

output:
{
  "@odata.id": "/redfish/v1/Managers/System/LogServices/EventLog/Entries",
  "@odata.type": "#LogEntryCollection.LogEntryCollection",
  "Description": "Collection of System Event Log Entries",
  "Members": [
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745913805",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:03:25+00:00",
      "EntryType": "Event",
      "Id": "1745913805",
      "Message": "Discrete event powerStateOn asserted",
      "MessageArgs": [
        "powerStateOn"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    },
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1745913805_1",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-04-29T08:03:25+00:00",
      "EntryType": "Event",
      "Id": "1745913805_1",
      "Message": "Discrete event chassisIntrusionRuntimeDetection asserted",
      "MessageArgs": [
        "chassisIntrusionRuntimeDetection"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    },
    ...
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1747027622_1",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-12T05:27:02+00:00",
      "EntryType": "Event",
      "Id": "1747027622_1",
      "Message": "Discrete event Bootstatus asserted",
      "MessageArgs": [
        "Bootstatus"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    }
  ],
  "Members@odata.count": 24,
  "Name": "System Event Log Entries"
}
```
# Using Compound filters $skip and $filter 
We can support the Skip and filters together.  Please note that the 

##Example curl script:
```bash
curl -k -H "Content-Type: application/json"  -u "admin":"admin"  -X GET "https://localhost/redfish/v1/Managers/System/LogServices/EventLog/Entries?\$skip=30&\$filter=
MessageId%20eq%20'OpenBMC.0.4.DiscreteEventAsserted'"

output:
{
  "@odata.id": "/redfish/v1/Managers/System/LogServices/EventLog/Entries",
  "@odata.type": "#LogEntryCollection.LogEntryCollection",
  "Description": "Collection of System Event Log Entries",
  "Members": [
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1747026963_1",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-12T05:16:03+00:00",
      "EntryType": "Event",
      "Id": "1747026963_1",
      "Message": "Discrete event chassisIntrusionRuntimeDetection asserted",
      "MessageArgs": [
        "chassisIntrusionRuntimeDetection"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    },
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1747026963_2",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-12T05:16:03+00:00",
      "EntryType": "Event",
      "Id": "1747026963_2",
      "Message": "Discrete event psuStatusFeedChange asserted",
      "MessageArgs": [
        "psuStatusFeedChange"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    },
    ...
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1747027622_1",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-12T05:27:02+00:00",
      "EntryType": "Event",
      "Id": "1747027622_1",
      "Message": "Discrete event Bootstatus asserted",
      "MessageArgs": [
        "Bootstatus"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    }
  ],
  "Members@odata.count": 7,
  "Name": "System Event Log Entries"
}
```
# Using Compound filters: $skip, $top, and $filter 
We can support this but please make sure the order of the filters is maintained.

##Example curl script:
```bash
curl -k -H "Content-Type: application/json" -u "admin":"admin" -X GET "https://localhost/redfish/v1/Managers/System/LogServices/EventLog/Entries?\$skip=30&\$top=1&\
$filter=MessageId%20eq%20'OpenBMC.0.4.DiscreteEventAsserted'"

output: 
{
  "@odata.id": "/redfish/v1/Managers/System/LogServices/EventLog/Entries",
  "@odata.type": "#LogEntryCollection.LogEntryCollection",
  "Description": "Collection of System Event Log Entries",
  "Members": [
    {
      "@odata.id": "/redfish/v1/Systems/system/LogServices/EventLog/Entries/1747026963_1",
      "@odata.type": "#LogEntry.v1_8_0.LogEntry",
      "Created": "2025-05-12T05:16:03+00:00",
      "EntryType": "Event",
      "Id": "1747026963_1",
      "Message": "Discrete event chassisIntrusionRuntimeDetection asserted",
      "MessageArgs": [
        "chassisIntrusionRuntimeDetection"
      ],
      "MessageId": "OpenBMC.0.4.DiscreteEventAsserted",
      "Name": "System Event Log Entry",
      "Severity": "OK"
    }
  ],
  "Members@odata.count": 1,
  "Members@odata.nextLink": "/redfish/v1/Managers/System/LogServices/EventLog/Entries?$skip=31",
  "Name": "System Event Log Entries"
}
```



