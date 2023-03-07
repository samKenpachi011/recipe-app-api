"""
Tests for recipe APIs
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient
import os
import tempfile
from PIL import Image

from core.models import Recipe, Tag, Ingredient
from recipe.serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
    )


RECIPE_URL = reverse('recipe:recipe-list')


def image_upload_url(recipe_id):
    """Create and return an image upload URL"""
    return reverse('recipe:recipe-upload-image', args=[recipe_id])


def create_recipe(user, **params):
    """Create and return a sample recipe"""
    defaults = {
        'title': 'Sample recipe title',
        'time_minutes': 22,
        'price': Decimal('5.25'),
        'description': 'Sample description',
        'link': 'https://example.com/recipe.pdf',
    }
    defaults.update(params)

    recipe = Recipe.objects.create(user=user, **defaults)
    return recipe


def detail_url(recipe_id):
    """Create and return a recipe detail URL"""
    return reverse('recipe:recipe-detail', args=[recipe_id])


def create_user(**params):
    """Create and return a new user"""
    return get_user_model().objects.create_user(**params)


class PublicRecipeAPITests(TestCase):
    """Test unautheticated API requests"""
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        """Test returns error for unauthorized users"""
        res = self.client.get(RECIPE_URL)

        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeAPITests(TestCase):
    """Test authenticated API requests"""

    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            'test@example.com',
            'testpassword123'
        )

        self.client.force_authenticate(self.user)

    def test_retrive_recipes(self):
        """Test authenticated user to get recipes"""
        create_recipe(user=self.user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPE_URL)

        recipes = Recipe.objects.all().order_by('-id')
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        """Test list of authenticated user limted to them"""
        other_user = create_user(
            email='other@example.com',
            password='otherpassword123'
        )

        create_recipe(user=other_user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPE_URL)

        recipes = Recipe.objects.filter(user=self.user)
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_get_recipe_detail(self):
        """Test get recipe detail"""
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.get(url)

        serializer = RecipeDetailSerializer(recipe)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, serializer.data)

    def test_create_recipe(self):
        """Test creating a recipe"""
        payload = {
            'title': 'Sample recipe',
            'time_minutes': 30,
            'price': Decimal('5.99'),
        }

        res = self.client.post(RECIPE_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipe = Recipe.objects.get(id=res.data['id'])

        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)

        self.assertEqual(recipe.user, self.user)

    def test_partial_update(self):
        """Test partial update of a recipe"""
        original_link = 'https://example.com/recipe.pdf'
        recipe = create_recipe(
            user=self.user,
            title='Sample recipe title',
            link=original_link,
        )

        payload = {
            'title': 'New recipe',
        }

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.user, self.user)
        self.assertEqual(recipe.title, payload['title'])
        self.assertEqual(recipe.link, original_link)

    def test_full_recipe_update(self):
        """Test full recipe update"""
        recipe = create_recipe(
            user=self.user,
            title='Sample recipe title',
            link='https://exmaple.com/recipe.pdf',
            description='Sample recipe description.',
        )

        payload = {
            'title': 'New recipe title',
            'link': 'https://example.com/new-recipe.pdf',
            'description': 'New recipe description',
            'time_minutes': 10,
            'price': Decimal('2.50'),
        }

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        for k, v in payload.items():
            self.assertEqual(getattr(recipe, k), v)
        self.assertEqual(recipe.user, self.user)

    def test_update_user_returns_error(self):
        """Test return error when updating recipe with another user"""
        new_user = create_user(
            email='newuser@example.com',
            password='newpass123'
        )

        recipe = create_recipe(
            user=self.user,
        )
        payload = {
            'user': new_user.id
        }

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEqual(recipe.user, self.user)

    def test_delete_recipe(self):
        """Test delete recipe"""
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_delete_other_users_recipe_error(self):
        """Test deleting another users recipe give error"""
        new_user = create_user(
            email="newuser2@example.com",
            password="newuser2pass123")

        recipe = create_recipe(user=new_user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id=recipe.id).exists())

    def test_create_recipe_with_new_tags(self):
        """Test create a recipe with tags"""
        payload = {
            'title': 'Thai Prawn Curry',
            'time_minutes': 30,
            'price': Decimal('2.50'),
            'tags': [{'name': 'Thai'}, {'name': 'Dinner'}],
        }

        res = self.client.post(RECIPE_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.tags.count(), 2)
        for tag in payload['tags']:
            exists = recipe.tags.filter(
                name=tag['name'],
                user=self.user).exists()
            self.assertTrue(exists)

    def test_create_recipe_with_existing_tags(self):
        """Test create recipe with existing tags"""
        tag_indian = Tag.objects.create(user=self.user, name='Indian')

        payload = {
            'title': 'Pongal',
            'time_minutes': 60,
            'price': Decimal('4.50'),
            'tags': [{'name': 'Indian'}, {'name': 'Breakfast'}],
        }

        res = self.client.post(RECIPE_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.tags.count(), 2)
        self.assertIn(tag_indian, recipe.tags.all())
        for tag in payload['tags']:
            exists = recipe.tags.filter(
                name=tag['name'],
                user=self.user).exists()
            self.assertTrue(exists)

    def test_create_tag_on_update(self):
        """Test create tag when updating a recipe"""
        recipe = create_recipe(user=self.user)

        payload = {'tags': [{'name': 'Lunch'}]}

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        tag = Tag.objects.get(user=self.user)
        self.assertIn(tag, recipe.tags.all())

    def test_update_recipe_assign_tag(self):
        """Test updating recipe with an exisiting tag"""
        tag_breakfast = Tag.objects.create(user=self.user, name='Breakfast')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag_breakfast)

        tag_lunch = Tag.objects.create(user=self.user, name='Lunch')
        payload = {'tags': [{'name': 'Lunch'}]}

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(tag_lunch, recipe.tags.all())
        self.assertNotIn(tag_breakfast, recipe.tags.all())

    def test_clear_recipe_tags(self):
        """Test clearing a recipes tags"""
        tag = Tag.objects.create(user=self.user, name='Dessert')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag)
        payload = {'tags': []}

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.tags.count(), 0)

    def test_creating_recipe_with_new_ingredient(self):
        """Tes creating a recipe with ingredients"""
        payload = {
            'title': 'Cauliflower Tacos',
            'time_minutes': 60,
            'price': Decimal('4.30'),
            'ingredient': [{'name': 'Cauliflower'}, {'name': 'Salt'}],
        }

        res = self.client.post(RECIPE_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEqual(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEqual(recipe.ingredient.count(), 2)
        for ingredient in payload['ingredient']:
            exist = recipe.ingredient.filter(
                user=self.user,
                name=ingredient['name']).exists()

            self.assertTrue(exist)

    def test_creating_recipe_with_existing_ingredient(self):
        """Test creating a recipe with existing ingredient"""

        ingredient = Ingredient.objects.create(
            user=self.user,
            name='Lemon'
        )

        payload = {
            'title': 'Cauliflower Tacos',
            'time_minutes': 60,
            'price': Decimal('4.30'),
            'ingredient': [{'name': 'Lemon'}, {'name': 'Salt'}],
        }

        res = self.client.post(RECIPE_URL, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        recipe = recipes[0]
        self.assertEqual(recipes.count(), 1)
        self.assertEqual(recipe.ingredient.count(), 2)
        self.assertIn(ingredient, recipe.ingredient.all())
        for ingredient in payload['ingredient']:
            exists = recipe.ingredient.filter(
                user=self.user,
                name=ingredient['name']).exists()

            self.assertTrue(exists)

    def test_create_ingredient_on_recipe_update(self):
        """Test create ingredient on recipe update"""

        recipe = create_recipe(user=self.user)
        payload = {'ingredient': [{'name': 'Limes'}]}

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_ingredient = Ingredient.objects.get(user=self.user, name='Limes')

        self.assertIn(new_ingredient, recipe.ingredient.all())

    def test_update_recipe_assing_ingredient(self):
        """Test assigning an existing ingredient when updating a recipe"""
        ingredient_1 = Ingredient.objects.create(user=self.user,
                                                 name='Pepper')
        recipe = create_recipe(user=self.user)
        payload = {'ingredient': [{'name': 'Chilli'}]}
        url = detail_url(recipe.id)
        ingredient_2 = Ingredient.objects.create(user=self.user,
                                                 name='Chilli')

        recipe.ingredient.add(ingredient_1)
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(ingredient_2, recipe.ingredient.all())
        self.assertNotIn(ingredient_1, recipe.ingredient.all())

    def test_clear_ingredient(self):
        """Test clear ingredient"""
        ingredient_1 = Ingredient.objects.create(user=self.user,
                                                 name='Garlic')
        recipe = create_recipe(self.user)
        recipe.ingredient.add(ingredient_1)

        url = detail_url(recipe.id)
        payload = {'ingredient': []}
        res = self.client.patch(url, payload, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(recipe.ingredient.count(), 0)

    def test_filter_by_tags(self):
        """Test to filter recipe by tags"""

        r1 = create_recipe(user=self.user, title='Thai Vegetable Curry')
        r2 = create_recipe(user=self.user, title='Aubergine with Tahini')
        r3 = create_recipe(user=self.user, title='Fish and chips')

        tag1 = Tag.objects.create(user=self.user, name='Vegan')
        tag2 = Tag.objects.create(user=self.user, name='Vegetarian')

        r1.tags.add(tag1)
        r2.tags.add(tag2)

        params = {'tags': f'{tag1.id}, {tag2.id}'}

        res = self.client.get(RECIPE_URL, params)

        s1 = RecipeSerializer(r1)
        s2 = RecipeSerializer(r2)
        s3 = RecipeSerializer(r3)

        self.assertIn(s1.data, res.data)
        self.assertIn(s2.data, res.data)
        self.assertNotIn(s3.data, res.data)

    def test_filter_by_ingredient(self):
        """Test to filter recipe by ingredient"""
        r1 = create_recipe(user=self.user, title='Posh Beans on Toast')
        r2 = create_recipe(user=self.user, title='Chicken Cacciatore')
        r3 = create_recipe(user=self.user, title='Red Lentil Daal')
        ing1 = Ingredient.objects.create(user=self.user, name='Feta Cheese')
        ing2 = Ingredient.objects.create(user=self.user, name='Chicken')
        r1.ingredient.add(ing1)
        r2.ingredient.add(ing2)

        params = {'ingredient': f'{ing1.id}, {ing2.id}'}

        res = self.client.get(RECIPE_URL, params)

        s1 = RecipeSerializer(r1)
        s2 = RecipeSerializer(r1)
        s3 = RecipeSerializer(r3)

        self.assertIn(s1.data, res.data)
        self.assertIn(s2.data, res.data)
        self.assertNotIn(s3.data, res.data)


class ImageUploadTests(TestCase):
    """Tests for uploading recipe image"""

    def setUp(self):
        self.client = APIClient()

        self.user = get_user_model().objects.create_user(
            email='user@example.com', password='testpass123')

        self.client.force_authenticate(self.user)

        self.recipe = create_recipe(user=self.user)

    def tearDown(self):
        self.recipe.image.delete()

    def test_upload_image_bad_request(self):
        """Test return error on bad image request"""

        url = image_upload_url(self.recipe.id)
        payload = {'image': 'noimage'}
        res = self.client.post(url, payload, format='multipart')

        self.assertEqual(res.status_code,  status.HTTP_400_BAD_REQUEST)

    def test_upload_image_success(self):
        """Test add image to recipe"""

        url = image_upload_url(self.recipe.id)
        with tempfile.NamedTemporaryFile(suffix='.jpg') as image_file:
            img = Image.new('RGB', (10, 10))
            img.save(image_file)
            image_file.seek(0)
            payload = {'image': image_file}

            res = self.client.post(url, payload, format='multipart')
            self.recipe.refresh_from_db()

            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertIn('image', res.data)

            self.assertTrue(os.path.exists(self.recipe.image.path))
