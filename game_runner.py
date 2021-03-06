"""CSC111 Final Project

Module containing the Game class used to run simulations for training.
"""
from copy import deepcopy
from typing import Type, Optional
import csv
import random
import pygame

from ai_neural_net import NeuralNetGraph
from game_state import Actor, ActorState, GameState
from vector import Vector

import ai_controls
import game_constants as const
import game_controls


class Game:
    """A class representing a game simulator.

    Instance Attributes:
        - clock: The clock used to wait between ticks if in visualized mode.
        - screen: The pygame screen used for drawing onto.
        - font: The font used for writing on screen.
        - state: The state of the current game.
        - grid: The map of the game tiles.
    """
    clock: pygame.time.Clock
    screen: Optional[pygame.Surface]
    font: Optional[pygame.font.Font]
    state: Optional[GameState]
    grid: list[list[int]]

    # Private Instance Attributes:
    #  - _default_grid: The original map grid before gameplay.
    _default_grid: list[list[int]]

    def __init__(self, map_path: str) -> None:
        """Initializes a game with the original pre-gameplay map.

        Args:
            - map_path: The directory for the map grid csv.
        """
        self.clock = pygame.time.Clock()
        self.screen = None
        self.font = None
        self.state = None

        # Load the map
        with open(map_path) as csv_file:
            reader = csv.reader(csv_file)
            self._default_grid = list(reader)
        self.grid = []

    def run(self, player_controller: Type[game_controls.Controller] = game_controls.InputController,
            neural_net: NeuralNetGraph = None, seed: Optional[int] = None,
            config: dict = None) -> dict:
        """Runs a game with given player controller, neural network, and configurations.
        Returns outcome of game as dict.

        Args:
            - player_controller: The class of the player controller to be used.
            - neural_net: The neural network to be used if and AIController is to be used.
            - seed: The random seed which allows for replaying successful runs.
            - config: The configuration dictionary for the game.
        """
        if config is None:
            config = {}
        if seed is not None:
            random.seed(seed)

        # Default configurations
        lives = config.get('lives', const.DEFAULT_LIVES)
        has_ghosts = config.get('has_ghosts', True)
        has_boosts = config.get('has_boosts', True)
        is_visual = config.get('is_visual', True)
        is_debug = config.get('is_debug', False)

        # Reinitialize the game state.
        self.state = GameState(lives)
        if has_ghosts:
            ghost_states = [ActorState(position, Vector(0, 0), colour, const.DEFAULT_SPEED)
                            for position, colour in zip(const.GHOST_POS, const.GHOST_COLOURS)]

            game_controls.BlinkyController(self.state, Actor(ghost_states[0], False))
            game_controls.PinkyController(self.state, Actor(ghost_states[1], False))
            game_controls.InkyController(self.state, Actor(ghost_states[2], False))
            game_controls.ClydeController(self.state, Actor(ghost_states[3], False))

        # Attach neural network if AI controlled.
        if issubclass(player_controller, ai_controls.AIController):
            player_controller(self.state, Actor(), neural_net)
        else:
            player_controller(self.state, Actor())

        # New copy of original grid.
        self.grid = deepcopy(self._default_grid)
        if not has_boosts:
            self.grid = [[const.DOT if tile == const.BOOST else tile for tile in row]
                         for row in self.grid]

        # Set up screen if visual.
        if is_visual:
            pygame.init()

            self.screen = pygame.display.set_mode(const.SCREEN_SIZE.tuple())
            self.font = pygame.font.SysFont('arial', 24)
            pygame.display.set_caption('Pac-Man!')

        # Start game loop
        game_over = False
        while not game_over:
            if self.handle_input():
                break

            game_over = self.update()

            if is_visual:
                self.draw(is_debug)
                self.clock.tick(const.FPS)

        # Set up the outputs of the simulation.
        output = {'game_win': self.check_win(), 'score': self.state.score,
                  'force_quit': not game_over}
        if issubclass(player_controller, ai_controls.AIController):
            output['time_alive'] = round(self.state.player().ticks_alive / const.FPS)

        return output

    def handle_input(self) -> bool:
        """Updates the input events of the game state, returns whether program is quit. """
        if not pygame.display.get_init():
            return False

        self.state.events = pygame.event.get()

        for event in self.state.events:
            if event.type == pygame.KEYDOWN:
                self.state.timers.start_timer = 0
            elif event.type == pygame.QUIT:
                return True
        return False

    def update(self) -> bool:
        """Updates the game and actor states, returns whether program is quit. """
        state = self.state
        # Check for start timer
        if state.timers.check_start():
            return False

        # Update other timers
        state.timers.update()

        # Control and update player
        state.player().control(self.grid)
        state.player_actor().update(self.grid)

        # Control and update ghosts
        for ghost in state.ghosts():
            if state.timers.check_boost():
                ghost.set_frightened(False)

            ghost.control(self.grid)
            ghost.actor.update(self.grid)

            # Ghost collisions
            is_collide = state.player_actor().rect().colliderect(ghost.actor.rect())
            if is_collide and ghost.get_frightened():
                # Eat ghost if they are frightened.
                ghost.set_frightened(False)
                ghost.home_timer = const.HOME_TIME
                ghost.state = 'home'

                ghost.actor.reset(const.HOME_POS)

                state.score += const.GHOST_SCORE[state.timers.boost_level]
                state.timers.boost_level += 1
            elif is_collide:
                # Lose a life if ghost is not frightened.
                self.lose_life()
                break

        # Tile collisions
        tile = state.player_actor().tile()
        if self.grid[tile.y][tile.x] == const.DOT:
            self.grid[tile.y][tile.x] = const.EMPTY
            state.score += const.DOT_SCORE
            state.dot_counter += 1
        elif self.grid[tile.y][tile.x] == const.BOOST:
            self.grid[tile.y][tile.x] = const.EMPTY
            state.score += const.BOOST_SCORE
            state.timers.set_boost()

            for ghost in state.ghosts():
                ghost.set_frightened(True)

        # Check win and lose conditions
        if state.lives <= 0 or self.check_win():
            return True
        else:
            return False

    def lose_life(self) -> None:
        """Handles losing a life and resets the game to a starting state. """
        state = self.state

        state.lost_life = True
        state.dot_counter = 0
        state.lives -= 1

        state.timers.set_start()
        state.timers.set_release()

        for controller in state.controllers:
            controller.reset()
            controller.actor.reset()

    def draw(self, is_debug: bool = False) -> None:
        """Draws the current game to the pygame screen.

        Args:
            - is_debug: Whether to draw debug information or not.
        """
        self.screen.fill((0, 0, 0))

        # Draw each tile in grid.
        for y, row in enumerate(self.grid):
            for x, tile in enumerate(row):
                self.draw_tile(tile, x, y, is_debug)

        # Draw debug information.
        if is_debug:
            self.draw_debug()

        # Draw actors.
        for ghost in self.state.ghosts():
            if ghost.home_timer <= 0:
                ghost.actor.draw(self.screen, is_debug)
        self.state.player_actor().draw(self.screen, is_debug)

        # Write out score.
        self.screen.blit(self.font.render(f'Score: {self.state.score}', 1,
                                          (255, 255, 255)), (5, 5))
        pygame.display.update()

    def draw_debug(self) -> None:
        """Draws controller debug information to the pygame screen. """
        for controller in self.state.controllers:
            controller.draw_debug(self.screen)

    def draw_tile(self, tile: str, x: int, y: int, debug: bool = False) -> None:
        """Draws the tile at position to the pygame screen.

        Args:
            - tile: The type of the tile to be drawn.
            - x: The x-coordinate of the tile to be drawn.
            - y: The y-coordinate of the tile to be drawn.
            - is_debug: Whether to draw debug information or not.
        """
        position = const.TILE_SIZE * (x, y)

        # Draws depending on the type of tile.
        if tile == const.WALL:
            pygame.draw.rect(self.screen, (0, 0, 255), pygame.Rect(*position, *const.TILE_SIZE))
        elif tile == const.DOOR:
            pygame.draw.rect(self.screen, (255, 150, 200), pygame.Rect(*position, *const.TILE_SIZE))
        elif tile == const.DOT:
            pygame.draw.circle(self.screen, (200, 200, 150),
                               (position + const.TILE_SIZE / 2).tuple(), 2)
        elif tile == const.BOOST:
            pygame.draw.circle(self.screen, (220, 220, 220),
                               (position + const.TILE_SIZE / 2).tuple(), 5)

        # Draw an overlay of grids.
        if debug:
            pygame.draw.rect(self.screen, (100, 100, 100),
                             pygame.Rect(*position, *const.TILE_SIZE), width=1)

    def check_win(self) -> bool:
        """Return if game is won, when all dots and boosts are eaten. """
        return not any(tile in {const.DOT, const.BOOST} for row in self.grid for tile in row)


if __name__ == '__main__':
    import python_ta
    python_ta.check_all(config={
        'extra-imports': ['copy', 'csv', 'random', 'pygame', 'ai_controls', 'ai_neural_net',
                          'game_constants', 'game_controls', 'game_state', 'vector'],
        'allowed-io': ['__init__'],
        'max-line-length': 100,
        'disable': ['E1136', 'E1101']
    })

    import python_ta.contracts
    python_ta.contracts.DEBUG_CONTRACTS = False
    python_ta.contracts.check_all_contracts()

    import doctest
    doctest.testmod()
