import threading
import pygame
import asyncio
import websockets
import json
import queue
import math

# the following is to avoid pygame.locals.K_UP but allow usage of K_UP
# from pygame.locals import *

WIDTH, HEIGHT = 640, 480
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
LIGHT_GREEN = (0, 255, 0)

class Robot(pygame.sprite.Sprite):
    def __init__(self):
        pygame.sprite.Sprite.__init__(self)        
        self.green_image = pygame.image.load("robot_green.png").convert_alpha()
        self.red_image = pygame.image.load("robot_red.png").convert_alpha()
        self.image = self.red_image
        self.rect = self.image.get_rect()
        self.rect.center = (WIDTH/2, HEIGHT/2) # Set the initial position of the sprite
        self.rotation_angle = 0 # Initialize the rotation angle to 0 degrees
        self.pen_down = False # Initialize the pen down state to False

async def rotate_robot_image(robot):
    if robot.pen_down:
        robot.image = pygame.transform.rotate(robot.green_image, -math.degrees(robot.rotation_angle))
    else:
        robot.image = pygame.transform.rotate(robot.red_image, -math.degrees(robot.rotation_angle))

async def rotate_robot(robot, direction):
    # Set the desired rotation speed in degrees per second
    rotation_speed = 2  # 45 degrees per second
    time_per_update = 0.1  # time between updates in seconds
    current_angle = robot.rotation_angle
    rotation_step = rotation_speed * time_per_update

    # Calculate the number of steps to rotate the robot
    num_steps = int(abs(direction - current_angle) / rotation_step)

    # Calculate the direction to rotate the robot
    if direction > current_angle:
        rotation_direction = 1
    else:
        rotation_direction = -1

    print("Rotating robot", num_steps, "steps of", rotation_step, "degrees in direction", rotation_direction)

    for i in range(num_steps):
        # Rotate the robot
        robot.rotation_angle += rotation_step * rotation_direction
        await rotate_robot_image(robot)
        robot.rect = robot.image.get_rect(center=robot.rect.center)
        await asyncio.sleep(time_per_update)

    # Rotate the robot to the final angle
    robot.rotation_angle = direction
    await rotate_robot_image(robot)
    robot.rect = robot.image.get_rect(center=robot.rect.center)                

async def move_robot(robot, x, y, oldX, oldY):
    # Calculate the distance and direction to move
    dx, dy = x - oldX, y - oldY
    distance = math.sqrt(dx**2 + dy**2)
    direction = math.atan2(dy, dx)

    #if the robot rotation angle is not the same as the new direction
    #then rotate the robot to the new direction

    if robot.rotation_angle != direction:
        print("Rotating robot from", robot.rotation_angle, " to", direction)
        await rotate_robot(robot, direction)    

    # Set the desired speed in pixels per second
    speed = 20  # 100 pixels per second

    # Calculate the time between updates and the number of steps
    time_per_update = 0.1  # time between updates in seconds
    num_steps = int(distance / (speed * time_per_update))

    # Initialize accumulated movement values
    accumulated_dx = 0
    accumulated_dy = 0

    print("Moving robot", num_steps, "steps of ", speed, "px/s in direction", direction)

    step_size = speed * time_per_update
    dx_step = step_size * math.cos(direction)
    dy_step = step_size * math.sin(direction)

    for i in range(num_steps):
        # Accumulate the movement
        accumulated_dx += dx_step
        accumulated_dy += dy_step

        # Move the robot
        if abs(accumulated_dx) >= 1 or abs(accumulated_dy) >= 1:
            robot.rect.move_ip(int(accumulated_dx), int(accumulated_dy))
            # Reset the accumulated movement values but keep the remainder
            accumulated_dx -= int(accumulated_dx)
            accumulated_dy -= int(accumulated_dy)
            
        await asyncio.sleep(time_per_update)
    
    # Move the robot to the final position
    robot.rect.center = (x, y)    
    # draw the line from the old position to the new position if the pen is down
    if robot.pen_down:
        pygame.draw.line(robot_lines_surface, BLACK, (oldX, oldY), (x, y), 3)

async def command_robot(robot, command_queue):
    while True:
        # Get the next command from the queue (blocks if the queue is empty)
        command = command_queue.get()

        # Process the command
        x, y, oldX, oldY = command
                
        print("Moving robot from", oldX, oldY, " to", x, y)

        # if the robot position is not the same as the new oldX, oldY at 1 pixel distance
        # then move the robot to the oldX, oldY position first
        if math.sqrt((robot.rect.center[0] - oldX)**2 + (robot.rect.center[1] - oldY)**2) > 1:
            print("Moving robot to", oldX, oldY)
            robot.pen_down = False
            await move_robot(robot, oldX, oldY, robot.rect.center[0], robot.rect.center[1])

        # Move the robot
        robot.pen_down = True
        await move_robot(robot, x, y, oldX, oldY)
      
        

async def handle_connection(websocket, path):
    print("New connection:", websocket.remote_address)
    
    try:
        async for message in websocket:
            print("Received message:", message)

            # Parse the received JSON message
            data = json.loads(message)
            command = data['type']

            # Process the drawing commands
            if command == 'goToXY':                
                #at this point we are not doing anything with the target_id. 
                # target_id = data["target"] 

                x, y = data['x'], data['y']
                oldX, oldY = data['oldX'], data['oldY']

                #update coordinates since the 0,0 is in the middle of the screen                
                # and Y axis is inverted so we need to invert the Y coordinate
                x = x + WIDTH/2
                y = HEIGHT/2 - y
                oldX = oldX + WIDTH/2
                oldY = HEIGHT/2 - oldY
                
                # Perform the goToXY action for the target with the given ID 
                # and draw the line on the screen (light green)
                pygame.draw.line(command_lines_surface, LIGHT_GREEN, (oldX, oldY), (x, y), 1)
                pygame.display.flip()

                # add the command to the queue
                command_queue.put((x, y, oldX, oldY))

            
            elif command == 'clear':
                screen.fill(WHITE)
                pygame.display.flip()
        
    except websockets.ConnectionClosed:
        print("Connection closed:", websocket.remote_address)

async def start_websocket_server():
    async with websockets.serve(handle_connection, 'localhost', 8765):
        print("WebSocket server started on port 8765")
        await asyncio.Future()  # run forever

def run_websocket_server():
    asyncio.run(start_websocket_server())

def run_robot():
    asyncio.run(command_robot(robot, command_queue))

#SendGotoXY command to the robot
async def send_gotoxy_command(oldX, oldY, x, y):
    # Send the command to the robot
    command = {
        "type": "goToXY",
        "x": x,
        "y": y,
        "oldX": oldX,
        "oldY": oldY
    }
    
    websocket = await websockets.connect('ws://localhost:8765')  
    # Send the command to the robot
    await websocket.send(json.dumps(command))
    await websocket.close()



# Create a queue for the drawing commands
command_queue = queue.Queue()

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Scratch Pen Drawing : Robot Map Simulation")
screen.fill(WHITE)
pygame.display.flip()

robot_group = pygame.sprite.Group()
robot = Robot()
robot_group.add(robot)


# Create a shared surface for the lines
command_lines_surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
robot_lines_surface = pygame.Surface(screen.get_size(), pygame.SRCALPHA)


# Start the WebSocket server in a separate thread
websocket_server_thread = threading.Thread(target=run_websocket_server, daemon=True)
websocket_server_thread.start()

# Start the robot in a separate thread
robot_thread = threading.Thread(target=run_robot, daemon=True)
robot_thread.start()

# Create a clock object to control the frame rate
clock = pygame.time.Clock()
desired_fps = 60

# Main loop
while True:
    # Limit the frame rate
    clock.tick(desired_fps)

    #if the user press the C key then clear the screen
    #if the user press the Q key then quit the program
    #if the user press the T key then we send a test command to the robot
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            exit()
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_c:
                command_lines_surface.fill(WHITE)
                robot_lines_surface.fill(WHITE)
                pygame.display.flip()
            elif event.key == pygame.K_q:
                pygame.quit()
                exit()
            elif event.key == pygame.K_t:
                #send a test command to the robot
                asyncio.run(send_gotoxy_command(100, 100, 100, -100))
                asyncio.run(send_gotoxy_command(100, -100, -100, -100))
                asyncio.run(send_gotoxy_command(-100, -100, -100, 100))
                asyncio.run(send_gotoxy_command(-100, 100, 100, 100))
                
    
    screen.fill(WHITE)

    # Draw the commad lines
    screen.blit(command_lines_surface, (0, 0))

    # Draw the robot lines
    screen.blit(robot_lines_surface, (0, 0))

    # Draw the robot    
    robot_group.draw(screen)

    # Update the display
    pygame.display.flip()

    