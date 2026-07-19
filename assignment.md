SDE Intern Assignment 
Note: The solution must be implemented in JavaScript or Python. 
Topic 
System Design (Low-Level Design) 
Question 1: User Payout Management System 
Design a comprehensive Low-Level Design (LLD) for a system that manages user payouts for affiliate sales. 
Problem Statement 
Every sale initially enters the system with the status Pending. 
The system should provide users with an Advance Payout equal to 10% of the earnings for all eligible 
pending sales. 
Later, an administrator reconciles the sales, updating each sale to one of the following statuses: 
● Approved 
● Rejected 
After reconciliation, the system should calculate the user's final payout by considering any advance payouts 
that have already been transferred. 
Business Rules 
1. Advance Payout 
● Every Pending sale is eligible for an advance payout of 10% of its earnings. 
● Once an advance payout has been successfully transferred, the same sale must never receive another 
advance payout, even if the advance payout job runs multiple times. 
2. Final Payout Calculation 
During reconciliation: 
Case 1 — Approved Sale 
If a sale was: 
● Pending 
● Earnings = ₹30 
● Advance paid = ₹3 
After reconciliation, if the sale becomes approved, the remaining payout should be: ₹30 - ₹3 = ₹27 
Case 2 — Rejected Sale 
If a sale was: 
● Pending 
● Earnings = ₹50 
● Advance paid = ₹5 
After reconciliation, if the sale becomes rejected, the user has already received ₹5 that they were not entitled to. 
Therefore, this amount must be adjusted against the user's final payout. 
Adjustment = -₹5 
3. Withdrawal Restrictions 
A user can make only one payout withdrawal every 24 hours. 
Question 2: Failed Payout Recovery 
Sometimes a payout initiated to the user may later be: 
● Cancelled 
● Rejected 
● Failed 
In such cases, the system should: 
● Credit the failed payout amount back into the user's withdrawable balance. 
● Allow the user to initiate another withdrawal for that amount. 
Reference Data 
Sales Table 
[ 
] 
{ 
} 
"userId": "john_doe", 
"brand": "brand_1", 
"status": "pending", 
"earning": 40 
Brands 
brand_1 
brand_2 
brand_3 
Possible Status Values 
pending 
approved 
rejected 
Terminology 
Pending 
The product has been purchased. 
Approved 
The product has been successfully delivered and the return period has ended. 
Rejected 
The purchased product was returned or cancelled. 
Design Freedom 
You are free to: 
● Modify the reference schema as required. 
● Introduce additional tables/collections. 
● Design APIs. 
● Define entities, relationships, indexes, and workflows. 
● Explain trade-offs and design decisions. 
Example 
Before Reconciliation 
[ 
{ 
"userId": "john_doe", 
"brand": "brand_1", 
"status": "pending", 
"earning": 40 
}, 
{ 
    "userId": "john_doe", 
    "brand": "brand_1", 
    "status": "pending", 
    "earning": 40 
  }, 
  { 
    "userId": "john_doe", 
    "brand": "brand_1", 
    "status": "pending", 
    "earning": 40 
  } 
] 
 
Total Pending Earnings 
₹120 
 
Advance Payout 
10% of ₹120 = ₹12 
 
After Reconciliation 
[ 
  { 
    "userId": "john_doe", 
    "brand": "brand_1", 
    "status": "rejected", 
    "earning": 40 
  }, 
  { 
    "userId": "john_doe", 
    "brand": "brand_1", 
    "status": "approved", 
    "earning": 40 
  }, 
  { 
    "userId": "john_doe", 
    "brand": "brand_1", 
    "status": "approved", 
    "earning": 40 
  } 
] 
 
Final Payout Calculation 
Sale Earnings Advance Paid Final Adjustment 
Rejected 
₹40 
₹4 
−₹4 
Approved 
Approved 
₹40 
₹40 
Total Final Payout 
−₹4 + ₹36 + ₹36 = ₹68 
Therefore, the user receives: 
Final Payout = ₹68 
₹4 
₹4 
Expected Deliverables 
The submission should include: 
1. Low-Level Design (LLD). 
2. Database schema(s) with relationships. 
₹36 
₹36 
3. Class design (or equivalent design in your chosen language). 
4. APIs/endpoints  
5. Handling of edge cases and failure scenarios. 
6. Working implementation in JavaScript or Python. 
7. Explanation of key design decisions and trade-offs.