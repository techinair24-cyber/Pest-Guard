
            }

            for solution in solutions

        ]

    }

@app.get(

    "/api/solutions/{pest_id}",

)

def get_solution(

    pest_id: str,

    db: Session = Depends(get_db),

):

    solution = (

        db.query(Solution)

        .filter(Solution.pest_id == pest_id)

        .first()

    )

    if not solution:

        raise HTTPException(

            status_code=404,

            detail="Solution not found for this pest",

        )

    return {

        "solution": {

            "pest_id": solution.pest_id,

            "title": solution.title,

            "description": solution.description,

            "recommended_action": solution.recommended_action,

            "prevention": solution.prevention,

        }

    }

# -------------------------------------------------------------------

# WebSocket

# -------------------------------------------------------------------

@app.websocket("/ws/detections")

async def detection_websocket(websocket: WebSocket):

    await manager.connect(websocket)

    try:

        while True:

            message = await websocket.receive_text()

            if message == "ping":

                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:

        print("WebSocket client disconnected")

        manager.disconnect(websocket)

    except Exception as error:

        print("WebSocket error:", repr(error))

        manager.disconnect(websocket)

# -------------------------------------------------------------------

# Root endpoint

# -------------------------------------------------------------------

@app.get("/")

def root():

    return {

        "message": "Pest Guard Backend is running",

        "docs": "/docs",

    }
